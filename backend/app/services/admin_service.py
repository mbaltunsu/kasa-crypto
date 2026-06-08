from __future__ import annotations

import hashlib
from http import HTTPStatus
from typing import TYPE_CHECKING

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.chain.client import ChainRpcError
from app.core.enums import ErrorCode
from app.models.tables import (
    Asset,
    DepositAddress,
    LedgerAccount,
    LedgerEntry,
    User,
    WithdrawalRequest,
)
from app.schemas.admin import ReserveAssetResponse, ReservesResponse
from app.schemas.nft import AdminMintNftResponse
from app.services import ledger
from app.services.errors import raise_api_error

if TYPE_CHECKING:
    from collections.abc import Callable

    from app.chain.types import BalanceClient


async def _liabilities(session: AsyncSession, asset: Asset) -> int:
    # Sum each user wallet's balance, then keep only the POSITIVE ones (finding #17). Clamping the
    # grand total instead would let a negative/anomalous account net against others and understate
    # the true liability — negative balances are operational exceptions, not a discount on reserves.
    per_account = (
        select(func.coalesce(func.sum(LedgerEntry.amount), 0).label("balance"))
        .join(LedgerAccount, LedgerAccount.id == LedgerEntry.account_id)
        .where(
            LedgerAccount.owner_type == "user",
            LedgerAccount.name == ledger.USER_WALLET_ACCOUNT,
            LedgerEntry.asset_id == asset.id,
        )
        .group_by(LedgerEntry.account_id)
        .subquery()
    )
    positive = case((per_account.c.balance > 0, per_account.c.balance), else_=0)
    statement = select(func.coalesce(func.sum(positive), 0))
    return int((await session.execute(statement)).scalar_one())


def _sum_onchain(
    client: BalanceClient,
    asset: Asset,
    addresses: list[str],
    *,
    fallback: int,
) -> int:
    try:
        if asset.type == "native":
            return sum(client.native_balance(address) for address in addresses)
        if asset.contract_address is not None:
            return sum(
                client.erc20_balance(token_address=asset.contract_address, address=address)
                for address in addresses
            )
    except ChainRpcError:
        return fallback
    return fallback


async def reserves(
    session: AsyncSession,
    *,
    hot_wallet_address: str | None = None,
    balance_factory: Callable[[int], BalanceClient] | None = None,
) -> ReservesResponse:
    """Proof-of-reserves: ledger liabilities (Σ user wallets) vs custodied on-chain balances.

    When `balance_factory` is provided the reserve figure sums the live native/ERC-20 balances of
    every deposit address plus the hot wallet; otherwise it falls back to liabilities (delta 0).
    """
    assets = (
        await session.execute(select(Asset).order_by(Asset.chain_id, Asset.symbol))
    ).scalars().all()
    deposit_addresses = list((await session.execute(select(DepositAddress.address))).scalars())
    custody_addresses = list(deposit_addresses)
    if hot_wallet_address is not None:
        custody_addresses.append(hot_wallet_address)

    clients: dict[int, BalanceClient] = {}
    rows: list[ReserveAssetResponse] = []
    for asset in assets:
        liabilities = await _liabilities(session, asset)
        chain_reserves = liabilities
        if balance_factory is not None and asset.type in {"native", "erc20"}:
            client = clients.get(asset.chain_id)
            if client is None:
                client = balance_factory(asset.chain_id)
                clients[asset.chain_id] = client
            chain_reserves = _sum_onchain(client, asset, custody_addresses, fallback=liabilities)
        rows.append(
            ReserveAssetResponse(
                asset_id=asset.id,
                liabilities=liabilities,
                reserves=chain_reserves,
                delta=chain_reserves - liabilities,
            ),
        )
    return ReservesResponse(assets=rows)


async def list_withdrawals(
    session: AsyncSession,
    *,
    offset: int,
    limit: int,
) -> list[WithdrawalRequest]:
    return list(
        (
            await session.execute(
                select(WithdrawalRequest)
                .order_by(WithdrawalRequest.created_at.desc(), WithdrawalRequest.id.desc())
                .offset(offset)
                .limit(limit),
            )
        ).scalars(),
    )


async def mint_nft_stub(
    session: AsyncSession,
    *,
    user_email: str,
    chain_id: int,
) -> AdminMintNftResponse:
    user = (
        await session.execute(select(User).where(User.email == user_email.strip().lower()))
    ).scalar_one_or_none()
    if user is None:
        raise_api_error(HTTPStatus.NOT_FOUND, ErrorCode.NOT_FOUND, "User not found")

    # Deterministic placeholder receipt: once DemoCollectible is deployed, this would sign
    # `mint(deposit_address)` from the hot wallet and return the real tx hash + token id.
    digest = hashlib.sha256(f"{user.id}:{chain_id}".encode()).hexdigest()
    return AdminMintNftResponse(tx_hash="0x" + digest, token_id=str(int(digest[:12], 16)))
