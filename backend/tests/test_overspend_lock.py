"""Concurrent-overspend serialization (finding #2).

The debit paths (withdrawal, transfer) read available balance and then post a debit. Without a lock
two concurrent requests can both pass the balance check and overspend. The fix takes a row lock on
the user's wallet ledger account BEFORE reading the balance (Postgres `FOR UPDATE`; a no-op on
SQLite, which serializes writers anyway). SQLite cannot reproduce the race, so we pin the two
verifiable properties: the lock helper's contract, and that the lock is acquired before the read.
"""

from __future__ import annotations

import pytest

pytest.importorskip("aiosqlite")

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import LedgerEntryType
from app.models.tables import Asset, User
from app.services import ledger
from app.services.transfer_service import create_transfer
from app.services.withdrawal_service import create_withdrawal
from tests.support import seed_asset, seed_user

CHAIN_ID = 11_155_111
DEST = "0x90F79bf6EB2c4f870365E785982E1f101E93b906"


async def _fund(session: AsyncSession, user: User, asset: Asset, amount: int) -> None:
    source = await ledger.get_or_create_account(session, asset=asset, name="src", owner_type="system")
    wallet = await ledger.get_user_wallet_account(session, user=user, asset=asset)
    await ledger.post(
        session, transaction_type=LedgerEntryType.DEPOSIT, idempotency_key=f"fund:{user.id}",
        ref_type="test", ref_id="fund",
        legs=[ledger.LedgerLeg(source, asset, -amount), ledger.LedgerLeg(wallet, asset, amount)],
    )


@pytest.mark.asyncio
async def test_lock_user_asset_returns_wallet_account_and_is_idempotent(session: AsyncSession) -> None:
    asset = await seed_asset(session, chain_id=CHAIN_ID, asset_type="native", symbol="ETH", decimals=18)
    user = await seed_user(session, email="a@example.com", hd_index=1)

    locked = await ledger.lock_user_asset(session, user=user, asset=asset)
    assert locked.owner_type == "user"
    assert locked.user_id == user.id

    again = await ledger.lock_user_asset(session, user=user, asset=asset)
    assert again.id == locked.id


@pytest.mark.asyncio
async def test_create_withdrawal_locks_funds_before_reading_balance(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    asset = await seed_asset(session, chain_id=CHAIN_ID, asset_type="native", symbol="ETH", decimals=18)
    user = await seed_user(session, email="a@example.com", hd_index=1)
    await _fund(session, user, asset, 100)

    calls: list[str] = []
    real_balance = ledger.available_balance

    async def spy_lock(session: AsyncSession, *, user, asset):  # type: ignore[no-untyped-def]
        calls.append("lock")
        return await ledger.get_user_wallet_account(session, user=user, asset=asset)

    async def spy_balance(session: AsyncSession, *, user, asset):  # type: ignore[no-untyped-def]
        calls.append("balance")
        return await real_balance(session, user=user, asset=asset)

    monkeypatch.setattr(ledger, "lock_user_asset", spy_lock, raising=False)
    monkeypatch.setattr(ledger, "available_balance", spy_balance)

    await create_withdrawal(
        session, user=user, asset_id=asset.id, to_address=DEST, amount=10, idempotency_key="w1",
    )
    assert calls and calls.index("lock") < calls.index("balance")


@pytest.mark.asyncio
async def test_create_transfer_locks_funds_before_reading_balance(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    asset = await seed_asset(session, chain_id=CHAIN_ID, asset_type="native", symbol="ETH", decimals=18)
    alice = await seed_user(session, email="alice@example.com", hd_index=1)
    await seed_user(session, email="bob@example.com", hd_index=2)
    await _fund(session, alice, asset, 100)

    calls: list[str] = []
    real_balance = ledger.available_balance

    async def spy_lock(session: AsyncSession, *, user, asset):  # type: ignore[no-untyped-def]
        calls.append("lock")
        return await ledger.get_user_wallet_account(session, user=user, asset=asset)

    async def spy_balance(session: AsyncSession, *, user, asset):  # type: ignore[no-untyped-def]
        calls.append("balance")
        return await real_balance(session, user=user, asset=asset)

    monkeypatch.setattr(ledger, "lock_user_asset", spy_lock, raising=False)
    monkeypatch.setattr(ledger, "available_balance", spy_balance)

    await create_transfer(
        session, sender=alice, to_email="bob@example.com", asset_id=asset.id, amount=10, idempotency_key="t1",
    )
    assert calls and calls.index("lock") < calls.index("balance")
