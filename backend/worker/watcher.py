"""Deposit watcher / indexer.

One logical watcher per chain scans new blocks for ERC-20 `Transfer` logs and native value
transfers addressed to known deposit addresses, records them idempotently in `onchain_deposits`,
credits the ledger once a deposit is buried under N confirmations, and reverses on reorg.

All chain I/O goes through the injected `WatcherClient` protocol, so this module is exercised
end-to-end in tests against a fake — no network, no web3 import.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.chain.types import NATIVE_LOG_INDEX
from app.core.enums import DepositStatus, LedgerEntryType
from app.models.tables import Asset, ChainCursor, DepositAddress, OnchainDeposit, User
from app.services import ledger

if TYPE_CHECKING:
    from app.chain.types import WatcherClient

__all__ = ["NATIVE_LOG_INDEX", "ScanReport", "run_scan"]

_DEPOSIT_REF_TYPE = "onchain_deposit"


@dataclass(frozen=True)
class ScanReport:
    recorded: int
    credited: int
    orphaned: int


@dataclass(frozen=True)
class ReorgReport:
    orphaned: int
    lowest_block: int | None  # smallest block number orphaned this pass (drives cursor rewind)


async def get_cursor(session: AsyncSession, chain_id: int) -> ChainCursor | None:
    return (
        await session.execute(select(ChainCursor).where(ChainCursor.chain_id == chain_id))
    ).scalar_one_or_none()


async def _deposit_address_owners(session: AsyncSession) -> dict[str, UUID]:
    rows = (
        await session.execute(select(DepositAddress.address, DepositAddress.user_id))
    ).all()
    return {address.lower(): user_id for address, user_id in rows}


async def _chain_assets(
    session: AsyncSession,
    chain_id: int,
) -> tuple[dict[str, Asset], Asset | None]:
    assets = (
        await session.execute(select(Asset).where(Asset.chain_id == chain_id))
    ).scalars().all()
    erc20_by_contract = {
        asset.contract_address.lower(): asset
        for asset in assets
        if asset.type == "erc20" and asset.contract_address is not None
    }
    native_asset = next((asset for asset in assets if asset.type == "native"), None)
    return erc20_by_contract, native_asset


async def _load_asset(session: AsyncSession, asset_id: UUID) -> Asset:
    return (
        await session.execute(select(Asset).where(Asset.id == asset_id))
    ).scalar_one()


async def _load_user(session: AsyncSession, user_id: UUID) -> User:
    return (await session.execute(select(User).where(User.id == user_id))).scalar_one()


async def _insert_if_new(session: AsyncSession, deposit: OnchainDeposit) -> bool:
    existing = (
        await session.execute(
            select(OnchainDeposit).where(
                OnchainDeposit.chain_id == deposit.chain_id,
                OnchainDeposit.tx_hash == deposit.tx_hash,
                OnchainDeposit.log_index == deposit.log_index,
            ),
        )
    ).scalar_one_or_none()
    if existing is None:
        session.add(deposit)
        await session.flush()
        return True
    if existing.status == DepositStatus.ORPHANED.value:
        # The same tx was re-mined after a reorg: resurrect the row at its new canonical block so it
        # gets re-credited. Bump credit_revision so the credit/reversal idempotency keys are fresh
        # even if the block re-converges to the SAME hash (block_hash is not unique across a
        # reorg-reconverge — keying credits on it silently swallowed the re-credit; see #6).
        existing.block_number = deposit.block_number
        existing.block_hash = deposit.block_hash
        existing.amount = deposit.amount
        existing.status = DepositStatus.SEEN.value
        existing.credit_revision = existing.credit_revision + 1
        await session.flush()
        return True
    return False


async def record_deposits(
    session: AsyncSession,
    client: WatcherClient,
    *,
    from_block: int,
    to_block: int,
) -> int:
    if from_block > to_block:
        return 0
    owners = await _deposit_address_owners(session)
    if not owners:
        return 0
    addresses = list(owners.keys())
    erc20_by_contract, native_asset = await _chain_assets(session, client.chain_id)
    recorded = 0

    if erc20_by_contract:
        transfers = client.fetch_erc20_transfers(
            token_addresses=list(erc20_by_contract.keys()),
            to_addresses=addresses,
            from_block=from_block,
            to_block=to_block,
        )
        for transfer in transfers:
            asset = erc20_by_contract.get(transfer.token_address.lower())
            user_id = owners.get(transfer.to_address.lower())
            if asset is None or user_id is None:
                continue
            deposit = OnchainDeposit(
                chain_id=client.chain_id,
                tx_hash=transfer.tx_hash,
                log_index=transfer.log_index,
                block_number=transfer.block_number,
                block_hash=transfer.block_hash,
                to_address=transfer.to_address,
                asset_id=asset.id,
                amount=transfer.value,
                status=DepositStatus.SEEN.value,
                user_id=user_id,
            )
            recorded += int(await _insert_if_new(session, deposit))

    if native_asset is not None:
        natives = client.fetch_native_transfers(
            to_addresses=addresses,
            from_block=from_block,
            to_block=to_block,
        )
        for native in natives:
            user_id = owners.get(native.to_address.lower())
            if user_id is None:
                continue
            deposit = OnchainDeposit(
                chain_id=client.chain_id,
                tx_hash=native.tx_hash,
                log_index=NATIVE_LOG_INDEX,
                block_number=native.block_number,
                block_hash=native.block_hash,
                to_address=native.to_address,
                asset_id=native_asset.id,
                amount=native.value,
                status=DepositStatus.SEEN.value,
                user_id=user_id,
            )
            recorded += int(await _insert_if_new(session, deposit))

    return recorded


async def _credit_deposit(session: AsyncSession, deposit: OnchainDeposit, user_id: UUID) -> None:
    asset = await _load_asset(session, deposit.asset_id)
    user = await _load_user(session, user_id)
    amount = int(deposit.amount)
    in_transit = await ledger.get_or_create_account(
        session, asset=asset, name=ledger.DEPOSITS_IN_TRANSIT_ACCOUNT, owner_type="system",
    )
    wallet = await ledger.get_user_wallet_account(session, user=user, asset=asset)
    await ledger.post(
        session,
        transaction_type=LedgerEntryType.DEPOSIT,
        idempotency_key=f"deposit-credit:{deposit.id}:{deposit.credit_revision}",
        ref_type=_DEPOSIT_REF_TYPE,
        ref_id=str(deposit.id),
        legs=[
            ledger.LedgerLeg(in_transit, asset, -amount),
            ledger.LedgerLeg(wallet, asset, amount),
        ],
    )


async def _reverse_credit(session: AsyncSession, deposit: OnchainDeposit, user_id: UUID) -> None:
    asset = await _load_asset(session, deposit.asset_id)
    user = await _load_user(session, user_id)
    amount = int(deposit.amount)
    in_transit = await ledger.get_or_create_account(
        session, asset=asset, name=ledger.DEPOSITS_IN_TRANSIT_ACCOUNT, owner_type="system",
    )
    wallet = await ledger.get_user_wallet_account(session, user=user, asset=asset)
    await ledger.post(
        session,
        transaction_type=LedgerEntryType.REVERSAL,
        idempotency_key=f"deposit-reverse:{deposit.id}:{deposit.credit_revision}",
        ref_type=_DEPOSIT_REF_TYPE,
        ref_id=str(deposit.id),
        legs=[
            ledger.LedgerLeg(wallet, asset, -amount),
            ledger.LedgerLeg(in_transit, asset, amount),
        ],
    )


async def confirm_and_credit(
    session: AsyncSession,
    client: WatcherClient,
    *,
    confirmations: int,
) -> int:
    chain_id = client.chain_id
    threshold = client.block_number() - confirmations

    final_seen = (
        await session.execute(
            select(OnchainDeposit).where(
                OnchainDeposit.chain_id == chain_id,
                OnchainDeposit.status == DepositStatus.SEEN.value,
                OnchainDeposit.block_number <= threshold,
            ),
        )
    ).scalars().all()
    for deposit in final_seen:
        deposit.status = DepositStatus.CONFIRMED.value
    await session.flush()

    confirmed = (
        await session.execute(
            select(OnchainDeposit).where(
                OnchainDeposit.chain_id == chain_id,
                OnchainDeposit.status == DepositStatus.CONFIRMED.value,
            ),
        )
    ).scalars().all()
    credited = 0
    for deposit in confirmed:
        if deposit.user_id is None:
            continue
        canonical = client.block_hash(deposit.block_number)
        if canonical is None:
            continue  # cannot verify the block right now → wait and retry next pass
        if canonical != deposit.block_hash:
            # Reorged out before we credited it: orphan without ever crediting (never credit off a
            # stale block hash).
            deposit.status = DepositStatus.ORPHANED.value
            continue
        await _credit_deposit(session, deposit, deposit.user_id)
        deposit.status = DepositStatus.CREDITED.value
        credited += 1
    await session.flush()
    return credited


async def handle_reorgs(
    session: AsyncSession,
    client: WatcherClient,
    *,
    reorg_depth: int,
) -> ReorgReport:
    chain_id = client.chain_id
    window_floor = client.block_number() - reorg_depth
    candidates = (
        await session.execute(
            select(OnchainDeposit).where(
                OnchainDeposit.chain_id == chain_id,
                OnchainDeposit.status.in_(
                    [
                        DepositStatus.SEEN.value,
                        DepositStatus.CONFIRMED.value,
                        DepositStatus.CREDITED.value,
                    ],
                ),
                OnchainDeposit.block_number > window_floor,
            ),
        )
    ).scalars().all()

    orphaned = 0
    lowest_block: int | None = None
    for deposit in candidates:
        canonical = client.block_hash(deposit.block_number)
        if canonical is None or canonical == deposit.block_hash:
            continue
        if deposit.status == DepositStatus.CREDITED.value and deposit.user_id is not None:
            await _reverse_credit(session, deposit, deposit.user_id)
        deposit.status = DepositStatus.ORPHANED.value
        orphaned += 1
        block = deposit.block_number
        lowest_block = block if lowest_block is None else min(lowest_block, block)
    await session.flush()
    return ReorgReport(orphaned=orphaned, lowest_block=lowest_block)


async def run_scan(
    session: AsyncSession,
    client: WatcherClient,
    *,
    confirmations: int,
    reorg_depth: int,
    finality_depth: int = 0,
    start_block: int = 0,
) -> ScanReport:
    chain_id = client.chain_id
    head = client.block_number()
    finalized = max(0, head - confirmations)

    cursor = await get_cursor(session, chain_id)
    if cursor is None:
        from_block = start_block
        cursor = ChainCursor(
            chain_id=chain_id,
            last_scanned_block=head,
            last_finalized_block=finalized,
        )
        session.add(cursor)
    else:
        from_block = cursor.last_scanned_block + 1
        cursor.last_scanned_block = max(cursor.last_scanned_block, head)
        cursor.last_finalized_block = finalized
    await session.flush()

    recorded = await record_deposits(session, client, from_block=from_block, to_block=head)
    credited = await confirm_and_credit(session, client, confirmations=confirmations)
    # The reorg window reaches confirmations (so a deposit that reorgs right after crediting is
    # caught) plus a finality margin, so a credited deposit stays reversible for a true finality
    # depth past the credit point — not merely `reorg_depth` blocks (finding #13). `finality_depth`
    # defaults to 0, falling back to reorg_depth, so existing call sites are unaffected.
    margin = max(reorg_depth, finality_depth)
    reorg = await handle_reorgs(session, client, reorg_depth=confirmations + margin)
    if reorg.lowest_block is not None:
        # Rewind so the replacement block(s) — which may carry new canonical deposits below the
        # cursor — get re-scanned next pass (record_deposits is idempotent on surviving txs).
        cursor.last_scanned_block = min(cursor.last_scanned_block, reorg.lowest_block - 1)
        await session.flush()
    return ScanReport(recorded=recorded, credited=credited, orphaned=reorg.orphaned)
