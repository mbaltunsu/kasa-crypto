"""Idempotency-key isolation: a client-supplied Idempotency-Key must never alias across
different operations or across users (findings #1 / #15).

Before the fix, the unique `ledger_transactions.idempotency_key` column was a *global* namespace:
- reusing a faucet/transfer key on a withdrawal made `ledger.post` return the foreign transaction
  WITHOUT posting the reservation debit, so the withdrawal broadcast with the user never debited;
- reusing a key across users leaked one user's transaction to another and skipped the second credit.
"""

from __future__ import annotations

from uuid import UUID

import pytest

pytest.importorskip("aiosqlite")

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import LedgerEntryType
from app.models.tables import WithdrawalRequest
from app.services import ledger
from app.services.transfer_service import create_transfer
from app.services.wallet_service import request_faucet
from app.services.withdrawal_service import create_withdrawal
from tests.support import seed_asset, seed_deposit_address, seed_user

CHAIN_ID = 11_155_111
ALICE_ADDR = "0x70997970C51812dc3A010C7d01b50e0d17dc79C8"
BOB_ADDR = "0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC"
DEST = "0x90F79bf6EB2c4f870365E785982E1f101E93b906"
ONE_ETH = 1_000_000_000_000_000_000


async def _account_balance(session: AsyncSession, account_id: UUID) -> int:
    from sqlalchemy import func

    from app.models.tables import LedgerEntry

    return int(
        (
            await session.execute(
                select(func.coalesce(func.sum(LedgerEntry.amount), 0)).where(
                    LedgerEntry.account_id == account_id,
                ),
            )
        ).scalar_one(),
    )


@pytest.mark.asyncio
async def test_withdrawal_reusing_a_faucet_key_still_debits_the_user(session: AsyncSession) -> None:
    """#1 P0: a withdrawal whose Idempotency-Key was already used by a faucet claim must NOT
    skip the reservation debit. The hot wallet must never pay out without debiting the user."""
    asset = await seed_asset(session, chain_id=CHAIN_ID, asset_type="native", symbol="ETH", decimals=18)
    alice = await seed_user(session, email="alice@example.com", hd_index=1)
    await seed_deposit_address(session, user=alice, address=ALICE_ADDR)

    # Fund alice with 2 ETH via the simulation faucet using a client key the attacker will reuse.
    await request_faucet(session, user=alice, asset_id=asset.id, amount=2 * ONE_ETH, idempotency_key="reuse-me")
    assert await ledger.available_balance(session, user=alice, asset=asset) == 2 * ONE_ETH

    # Reuse the SAME client key on a withdrawal of 1 ETH.
    response = await create_withdrawal(
        session, user=alice, asset_id=asset.id, to_address=DEST, amount=ONE_ETH, idempotency_key="reuse-me",
    )

    # The user is debited 1 ETH (available 2 -> 1) and 1 ETH is held in the reservation account.
    assert await ledger.available_balance(session, user=alice, asset=asset) == ONE_ETH
    reserved = await ledger.get_or_create_account(
        session, asset=asset, name=ledger.WITHDRAWALS_RESERVED_ACCOUNT, owner_type="system",
    )
    assert await _account_balance(session, reserved.id) == ONE_ETH
    request = (
        await session.execute(select(WithdrawalRequest).where(WithdrawalRequest.id == response.id))
    ).scalar_one()
    assert int(request.amount) == ONE_ETH


@pytest.mark.asyncio
async def test_transfer_reusing_a_faucet_key_is_not_aliased(session: AsyncSession) -> None:
    """#15: a transfer whose key collides with a prior faucet must actually move funds, not
    short-circuit and return the foreign transaction as a fake CONFIRMED."""
    asset = await seed_asset(session, chain_id=CHAIN_ID, asset_type="native", symbol="ETH", decimals=18)
    alice = await seed_user(session, email="alice@example.com", hd_index=1)
    bob = await seed_user(session, email="bob@example.com", hd_index=2)
    await seed_deposit_address(session, user=alice, address=ALICE_ADDR)

    await request_faucet(session, user=alice, asset_id=asset.id, amount=100, idempotency_key="dup")
    await create_transfer(
        session, sender=alice, to_email="bob@example.com", asset_id=asset.id, amount=30, idempotency_key="dup",
    )

    assert await ledger.available_balance(session, user=alice, asset=asset) == 70
    assert await ledger.available_balance(session, user=bob, asset=asset) == 30


@pytest.mark.asyncio
async def test_same_key_across_users_does_not_leak_or_skip_credit(session: AsyncSession) -> None:
    """#15 cross-user: two users using the same client key must each be credited independently;
    user B must never receive user A's transaction id / hash."""
    asset = await seed_asset(session, chain_id=CHAIN_ID, asset_type="native", symbol="ETH", decimals=18)
    alice = await seed_user(session, email="alice@example.com", hd_index=1)
    bob = await seed_user(session, email="bob@example.com", hd_index=2)
    await seed_deposit_address(session, user=alice, address=ALICE_ADDR)
    await seed_deposit_address(session, user=bob, address=BOB_ADDR)

    a = await request_faucet(session, user=alice, asset_id=asset.id, amount=5, idempotency_key="shared")
    b = await request_faucet(session, user=bob, asset_id=asset.id, amount=7, idempotency_key="shared")

    assert a.tx_hash != b.tx_hash
    assert await ledger.available_balance(session, user=alice, asset=asset) == 5
    assert await ledger.available_balance(session, user=bob, asset=asset) == 7


@pytest.mark.asyncio
async def test_ledger_post_rejects_same_key_for_a_different_operation(session: AsyncSession) -> None:
    """Defense in depth: ledger.post must refuse to replay a key against a different (ref_type, ref_id)
    rather than silently returning the unrelated transaction and posting nothing."""
    asset = await seed_asset(session, chain_id=CHAIN_ID, asset_type="native", symbol="ETH", decimals=18)
    src = await ledger.get_or_create_account(session, asset=asset, name="src", owner_type="system")
    dst = await ledger.get_or_create_account(session, asset=asset, name="dst", owner_type="system")

    await ledger.post(
        session, transaction_type=LedgerEntryType.ADJUSTMENT, idempotency_key="k",
        ref_type="op_a", ref_id="1",
        legs=[ledger.LedgerLeg(src, asset, -10), ledger.LedgerLeg(dst, asset, 10)],
    )
    # Same key, different operation -> must raise, not silently no-op.
    with pytest.raises(ledger.LedgerInvariantError):
        await ledger.post(
            session, transaction_type=LedgerEntryType.WITHDRAWAL, idempotency_key="k",
            ref_type="op_b", ref_id="2",
            legs=[ledger.LedgerLeg(src, asset, -10), ledger.LedgerLeg(dst, asset, 10)],
        )
    # Same key, same operation -> genuine idempotent replay still returns the original.
    replay = await ledger.post(
        session, transaction_type=LedgerEntryType.ADJUSTMENT, idempotency_key="k",
        ref_type="op_a", ref_id="1",
        legs=[ledger.LedgerLeg(src, asset, -10), ledger.LedgerLeg(dst, asset, 10)],
    )
    assert replay.ref_type == "op_a"
