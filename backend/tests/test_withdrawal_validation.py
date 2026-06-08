"""Withdrawal destination-address validation (finding #14).

The destination was accepted as any 1..128-char string and only normalized at broadcast time via
`to_checksum_address`, which (a) happily accepts the zero/burn address and (b) silently re-checksums
a mistyped mixed-case address instead of rejecting it — both irreversible fund-loss paths. Validate
at request time: reject non-EVM shapes, the zero address, and mixed-case EIP-55 checksum failures.
"""

from __future__ import annotations

import pytest

pytest.importorskip("aiosqlite")
pytest.importorskip("eth_utils")

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ErrorCode, LedgerEntryType
from app.models.tables import Asset, User, WithdrawalRequest
from app.services import ledger
from app.services.withdrawal_service import create_withdrawal
from tests.support import seed_asset, seed_user

CHAIN_ID = 11_155_111
VALID = "0x70997970C51812dc3A010C7d01b50e0d17dc79C8"  # canonical EIP-55 (Hardhat #1)
LOWER = VALID.lower()
ZERO = "0x" + "0" * 40
BAD_CHECKSUM = "0x70997970c51812dc3A010C7d01b50e0d17dc79C8"  # one nibble case-flipped from VALID


async def _fund(session: AsyncSession, user: User, asset: Asset, amount: int) -> None:
    source = await ledger.get_or_create_account(session, asset=asset, name="src", owner_type="system")
    wallet = await ledger.get_user_wallet_account(session, user=user, asset=asset)
    await ledger.post(
        session, transaction_type=LedgerEntryType.DEPOSIT, idempotency_key=f"fund:{user.id}",
        ref_type="test", ref_id="fund",
        legs=[ledger.LedgerLeg(source, asset, -amount), ledger.LedgerLeg(wallet, asset, amount)],
    )


async def _setup(session: AsyncSession) -> tuple[Asset, User]:
    asset = await seed_asset(session, chain_id=CHAIN_ID, asset_type="native", symbol="ETH", decimals=18)
    user = await seed_user(session, email="a@example.com", hd_index=1)
    await _fund(session, user, asset, 100)
    return asset, user


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [ZERO, BAD_CHECKSUM, "0xnothex", "0x1234", VALID + "00"])
async def test_withdrawal_rejects_invalid_destination(session: AsyncSession, bad: str) -> None:
    asset, user = await _setup(session)
    with pytest.raises(HTTPException) as excinfo:
        await create_withdrawal(
            session, user=user, asset_id=asset.id, to_address=bad, amount=10, idempotency_key="k",
        )
    assert excinfo.value.status_code == 422
    assert excinfo.value.detail["code"] == ErrorCode.VALIDATION_ERROR.value  # type: ignore[index]
    # The user is never debited and no withdrawal row is created for a rejected destination.
    assert await ledger.available_balance(session, user=user, asset=asset) == 100
    assert (await session.execute(select(WithdrawalRequest))).first() is None


@pytest.mark.asyncio
async def test_withdrawal_normalizes_lowercase_destination_to_checksum(session: AsyncSession) -> None:
    asset, user = await _setup(session)
    response = await create_withdrawal(
        session, user=user, asset_id=asset.id, to_address=LOWER, amount=10, idempotency_key="k",
    )
    request = (
        await session.execute(select(WithdrawalRequest).where(WithdrawalRequest.id == response.id))
    ).scalar_one()
    assert request.to_address == VALID  # stored in canonical EIP-55 form


@pytest.mark.asyncio
async def test_withdrawal_accepts_valid_checksummed_destination(session: AsyncSession) -> None:
    asset, user = await _setup(session)
    response = await create_withdrawal(
        session, user=user, asset_id=asset.id, to_address=VALID, amount=10, idempotency_key="k",
    )
    request = (
        await session.execute(select(WithdrawalRequest).where(WithdrawalRequest.id == response.id))
    ).scalar_one()
    assert request.to_address == VALID
