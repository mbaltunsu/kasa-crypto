from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.enums import DepositStatus, LedgerEntryType
from app.models.tables import (
    Asset,
    LedgerAccount,
    LedgerEntry,
    LedgerTransaction,
    OnchainDeposit,
    User,
)

USER_WALLET_ACCOUNT = "wallet"
# System (owner_type='system') account names. Centralized so the watcher, withdrawer, faucet,
# and reserves report all reference one spelling each (no string drift across services).
FAUCET_SOURCE_ACCOUNT = "faucet_source"
DEPOSITS_IN_TRANSIT_ACCOUNT = "deposits_in_transit"
WITHDRAWALS_RESERVED_ACCOUNT = "withdrawals_reserved"
WITHDRAWALS_SETTLED_ACCOUNT = "withdrawals_settled"


@dataclass(frozen=True)
class LedgerLeg:
    account: LedgerAccount
    asset: Asset
    amount: int


class LedgerInvariantError(ValueError):
    pass


async def _select_account(
    session: AsyncSession,
    *,
    owner_type: str,
    user_id: UUID | None,
    asset_id: UUID,
    name: str,
) -> LedgerAccount | None:
    # `.first()` (not scalar_one_or_none): `system` accounts have a NULL user_id, which Postgres
    # treats as distinct in the unique constraint, so duplicates are possible — never crash on them
    # (finding #10). A partial unique index (migration 0004) prevents new duplicates on Postgres.
    statement: Select[tuple[LedgerAccount]] = (
        select(LedgerAccount)
        .where(
            LedgerAccount.owner_type == owner_type,
            LedgerAccount.user_id == user_id,
            LedgerAccount.asset_id == asset_id,
            LedgerAccount.name == name,
        )
        .limit(1)
    )
    return (await session.execute(statement)).scalars().first()


async def get_or_create_account(
    session: AsyncSession,
    *,
    asset: Asset,
    name: str,
    owner_type: str,
    user: User | None = None,
) -> LedgerAccount:
    user_id = user.id if user is not None else None
    account = await _select_account(
        session, owner_type=owner_type, user_id=user_id, asset_id=asset.id, name=name,
    )
    if account is not None:
        return account

    account = LedgerAccount(owner_type=owner_type, user_id=user_id, asset_id=asset.id, name=name)
    try:
        # Insert inside a SAVEPOINT so a concurrent create that wins the race only rolls back THIS
        # insert (not the caller's other pending work), then fall back to the existing row.
        async with session.begin_nested():
            session.add(account)
            await session.flush()
    except IntegrityError:
        existing = await _select_account(
            session, owner_type=owner_type, user_id=user_id, asset_id=asset.id, name=name,
        )
        if existing is None:
            raise
        return existing
    return account


async def get_user_wallet_account(
    session: AsyncSession,
    *,
    user: User,
    asset: Asset,
) -> LedgerAccount:
    return await get_or_create_account(
        session,
        asset=asset,
        name=USER_WALLET_ACCOUNT,
        owner_type="user",
        user=user,
    )


def _supports_row_locks(session: AsyncSession) -> bool:
    try:
        return session.get_bind().dialect.name == "postgresql"
    except Exception:  # noqa: BLE001 - dialect probe is best-effort; default to no row locking
        return False


async def lock_user_asset(session: AsyncSession, *, user: User, asset: Asset) -> LedgerAccount:
    """Serialize concurrent debits for one (user, asset) before a check-then-debit.

    Acquires a row lock on the user's wallet ledger account so two requests can't both read the same
    available balance and both post a debit (overspend). Postgres uses `SELECT ... FOR UPDATE`; on
    SQLite the clause is skipped (writers are already serialized, so the race cannot occur there).
    Callers MUST take this lock before reading `available_balance` and keep both in one transaction.
    """
    account = await get_user_wallet_account(session, user=user, asset=asset)
    if _supports_row_locks(session):
        await session.execute(
            select(LedgerAccount.id).where(LedgerAccount.id == account.id).with_for_update(),
        )
    return account


async def find_transaction_by_idempotency_key(
    session: AsyncSession,
    idempotency_key: str,
) -> LedgerTransaction | None:
    statement = (
        select(LedgerTransaction)
        .options(selectinload(LedgerTransaction.entries))
        .where(LedgerTransaction.idempotency_key == idempotency_key)
    )
    return (await session.execute(statement)).scalar_one_or_none()


def _validate_legs(legs: Sequence[LedgerLeg]) -> None:
    if not legs:
        msg = "ledger transaction requires at least one leg"
        raise LedgerInvariantError(msg)

    totals: dict[UUID, int] = defaultdict(int)
    for leg in legs:
        if leg.account.asset_id != leg.asset.id:
            msg = "ledger leg account asset does not match leg asset"
            raise LedgerInvariantError(msg)
        totals[leg.asset.id] += leg.amount

    nonzero = {asset_id: total for asset_id, total in totals.items() if total != 0}
    if nonzero:
        msg = f"ledger transaction does not sum to zero per asset: {nonzero}"
        raise LedgerInvariantError(msg)


def _assert_replay_compatible(
    existing: LedgerTransaction,
    *,
    ref_type: str,
    ref_id: str,
) -> None:
    """An idempotency key may only ever be replayed for the *same* operation. A key found under a
    different (ref_type, ref_id) means the caller reused it for an unrelated request; returning the
    foreign transaction would silently skip the intended legs (custody loss), so refuse it."""
    if existing.ref_type != ref_type or existing.ref_id != ref_id:
        msg = (
            f"idempotency key already used for a different operation "
            f"({existing.ref_type}:{existing.ref_id}, not {ref_type}:{ref_id})"
        )
        raise LedgerInvariantError(msg)


async def post(
    session: AsyncSession,
    *,
    transaction_type: LedgerEntryType,
    idempotency_key: str,
    legs: Sequence[LedgerLeg],
    ref_type: str,
    ref_id: str,
) -> LedgerTransaction:
    existing = await find_transaction_by_idempotency_key(session, idempotency_key)
    if existing is not None:
        _assert_replay_compatible(existing, ref_type=ref_type, ref_id=ref_id)
        return existing

    _validate_legs(legs)
    transaction = LedgerTransaction(
        type=transaction_type.value,
        ref_type=ref_type,
        ref_id=ref_id,
        idempotency_key=idempotency_key,
    )
    session.add(transaction)
    await session.flush()

    for leg in legs:
        session.add(
            LedgerEntry(
                transaction_id=transaction.id,
                account_id=leg.account.id,
                asset_id=leg.asset.id,
                amount=leg.amount,
            ),
        )

    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        replay = await find_transaction_by_idempotency_key(session, idempotency_key)
        if replay is not None:
            _assert_replay_compatible(replay, ref_type=ref_type, ref_id=ref_id)
            return replay
        raise

    await session.refresh(transaction, attribute_names=["entries"])
    return transaction


async def available_balance(session: AsyncSession, *, user: User, asset: Asset) -> int:
    account_statement = select(LedgerAccount.id).where(
        LedgerAccount.owner_type == "user",
        LedgerAccount.user_id == user.id,
        LedgerAccount.asset_id == asset.id,
        LedgerAccount.name == USER_WALLET_ACCOUNT,
    )
    account_id = (await session.execute(account_statement)).scalar_one_or_none()
    if account_id is None:
        return 0

    amount_statement = select(func.coalesce(func.sum(LedgerEntry.amount), 0)).where(
        LedgerEntry.account_id == account_id,
        LedgerEntry.asset_id == asset.id,
    )
    return int((await session.execute(amount_statement)).scalar_one())


async def pending_balance(session: AsyncSession, *, user: User, asset: Asset) -> int:
    amount_statement = select(func.coalesce(func.sum(OnchainDeposit.amount), 0)).where(
        OnchainDeposit.user_id == user.id,
        OnchainDeposit.asset_id == asset.id,
        OnchainDeposit.status.in_([DepositStatus.SEEN.value, DepositStatus.CONFIRMED.value]),
    )
    return int((await session.execute(amount_statement)).scalar_one())


async def balance(session: AsyncSession, *, user: User, asset: Asset) -> tuple[int, int]:
    return (
        await available_balance(session, user=user, asset=asset),
        await pending_balance(session, user=user, asset=asset),
    )
