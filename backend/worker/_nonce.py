"""Shared hot-wallet nonce allocation for every outbox spending from the custody key."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError

from app.models.tables import HotWalletNonce

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.chain.types import SenderClient


def supports_skip_locked(session: AsyncSession) -> bool:
    try:
        return bool(session.get_bind().dialect.name == "postgresql")
    except Exception:  # noqa: BLE001 - dialect probe is best-effort; default to no row locking
        return False


async def select_nonce_row(session: AsyncSession, chain_id: int) -> HotWalletNonce | None:
    statement: Select[tuple[HotWalletNonce]] = select(HotWalletNonce).where(
        HotWalletNonce.chain_id == chain_id,
    )
    if supports_skip_locked(session):
        statement = statement.with_for_update()
    return (await session.execute(statement)).scalar_one_or_none()


async def nonce_row(
    session: AsyncSession,
    client: SenderClient,
    hot_wallet_address: str,
) -> HotWalletNonce:
    chain_id = client.chain_id
    row = await select_nonce_row(session, chain_id)
    chain_nonce = client.pending_nonce(hot_wallet_address)
    if row is None:
        # Create inside a SAVEPOINT so a concurrent first-spend pass that wins the race only rolls
        # back THIS insert; then fall back to the winner's row.
        new_row = HotWalletNonce(
            chain_id=chain_id, address=hot_wallet_address, next_nonce=chain_nonce,
        )
        try:
            async with session.begin_nested():
                session.add(new_row)
                await session.flush()
        except IntegrityError:
            row = await select_nonce_row(session, chain_id)
            if row is None:
                raise
        else:
            return new_row
    if row.address != hot_wallet_address:
        row.address = hot_wallet_address
        row.next_nonce = chain_nonce
    else:
        row.next_nonce = max(row.next_nonce, chain_nonce)
    await session.flush()
    return row
