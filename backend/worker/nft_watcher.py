"""NFT deposit watcher / indexer.

Scans ERC-721 `Transfer` logs to known deposit addresses, records them idempotently in
`nft_deposits`, creates `nft_holdings` once confirmed, and removes those holdings if the crediting
block reorgs away. NFTs intentionally bypass the double-entry amount ledger.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from kasa_shared.registry import nfts_of_chain
from sqlalchemy import func, select

from app.core.enums import NftDepositStatus, NftHoldingStatus
from app.models.tables import ChainCursor, NftDeposit, NftHolding
from worker.watcher import _deposit_address_owners, get_cursor

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.chain.types import WatcherClient

__all__ = [
    "NftScanReport",
    "confirm_and_credit_nfts",
    "handle_reorgs",
    "record_nft_deposits",
    "run_scan",
]


@dataclass(frozen=True)
class NftScanReport:
    recorded: int
    credited: int
    orphaned: int


@dataclass(frozen=True)
class NftReorgReport:
    orphaned: int
    lowest_block: int | None


async def _insert_if_new(session: AsyncSession, deposit: NftDeposit) -> bool:
    existing = (
        await session.execute(
            select(NftDeposit).where(
                NftDeposit.chain_id == deposit.chain_id,
                NftDeposit.tx_hash == deposit.tx_hash,
                NftDeposit.log_index == deposit.log_index,
            ),
        )
    ).scalar_one_or_none()
    if existing is None:
        session.add(deposit)
        await session.flush()
        return True
    if existing.status == NftDepositStatus.ORPHANED.value:
        # The same tx was re-mined after a reorg: resurrect the row at its new canonical block so it
        # gets re-credited. Bump credit_revision for parity with fungible deposits and to make the
        # re-credit observable even if the block re-converges to the same hash.
        existing.block_number = deposit.block_number
        existing.block_hash = deposit.block_hash
        existing.contract = deposit.contract
        existing.token_id = deposit.token_id
        existing.from_address = deposit.from_address
        existing.to_address = deposit.to_address
        existing.user_id = deposit.user_id
        existing.status = NftDepositStatus.SEEN.value
        existing.credit_revision = existing.credit_revision + 1
        await session.flush()
        return True
    return False


async def record_nft_deposits(
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
    contracts = [asset.address for asset in nfts_of_chain(client.chain_id)]
    if not contracts:
        return 0

    recorded = 0
    transfers = client.fetch_erc721_transfers(
        contract_addresses=contracts,
        to_addresses=list(owners.keys()),
        from_block=from_block,
        to_block=to_block,
    )
    for transfer in transfers:
        user_id = owners.get(transfer.to_address.lower())
        if user_id is None:
            continue
        deposit = NftDeposit(
            user_id=user_id,
            chain_id=client.chain_id,
            contract=transfer.contract_address,
            token_id=transfer.token_id,
            from_address=transfer.from_address,
            to_address=transfer.to_address,
            tx_hash=transfer.tx_hash,
            log_index=transfer.log_index,
            block_number=transfer.block_number,
            block_hash=transfer.block_hash,
            status=NftDepositStatus.SEEN.value,
        )
        recorded += int(await _insert_if_new(session, deposit))
    return recorded


async def _upsert_holding(
    session: AsyncSession,
    *,
    deposit: NftDeposit,
    user_id: UUID,
) -> None:
    existing = (
        await session.execute(
            select(NftHolding).where(
                NftHolding.chain_id == deposit.chain_id,
                func.lower(NftHolding.contract) == deposit.contract.lower(),
                NftHolding.token_id == deposit.token_id,
            ),
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.user_id = user_id
        existing.status = NftHoldingStatus.HELD.value
        return
    session.add(
        NftHolding(
            user_id=user_id,
            chain_id=deposit.chain_id,
            contract=deposit.contract,
            token_id=deposit.token_id,
            status=NftHoldingStatus.HELD.value,
        ),
    )


async def _remove_holding(session: AsyncSession, deposit: NftDeposit) -> None:
    existing = (
        await session.execute(
            select(NftHolding).where(
                NftHolding.chain_id == deposit.chain_id,
                func.lower(NftHolding.contract) == deposit.contract.lower(),
                NftHolding.token_id == deposit.token_id,
            ),
        )
    ).scalar_one_or_none()
    if existing is not None:
        await session.delete(existing)


async def confirm_and_credit_nfts(
    session: AsyncSession,
    client: WatcherClient,
    *,
    confirmations: int,
) -> int:
    chain_id = client.chain_id
    threshold = client.block_number() - confirmations

    final_seen = (
        await session.execute(
            select(NftDeposit).where(
                NftDeposit.chain_id == chain_id,
                NftDeposit.status == NftDepositStatus.SEEN.value,
                NftDeposit.block_number <= threshold,
            ),
        )
    ).scalars().all()
    for deposit in final_seen:
        deposit.status = NftDepositStatus.CONFIRMED.value
    await session.flush()

    confirmed = (
        await session.execute(
            select(NftDeposit).where(
                NftDeposit.chain_id == chain_id,
                NftDeposit.status == NftDepositStatus.CONFIRMED.value,
            ),
        )
    ).scalars().all()
    credited = 0
    for deposit in confirmed:
        if deposit.user_id is None:
            continue
        canonical = client.block_hash(deposit.block_number)
        if canonical is None:
            continue
        if canonical != deposit.block_hash:
            # Reorged out before we credited it: orphan without ever creating a holding.
            deposit.status = NftDepositStatus.ORPHANED.value
            continue
        await _upsert_holding(session, deposit=deposit, user_id=deposit.user_id)
        deposit.status = NftDepositStatus.CREDITED.value
        credited += 1
    await session.flush()
    return credited


async def handle_reorgs(
    session: AsyncSession,
    client: WatcherClient,
    *,
    reorg_depth: int,
) -> NftReorgReport:
    chain_id = client.chain_id
    window_floor = client.block_number() - reorg_depth
    candidates = (
        await session.execute(
            select(NftDeposit).where(
                NftDeposit.chain_id == chain_id,
                NftDeposit.status.in_(
                    [
                        NftDepositStatus.SEEN.value,
                        NftDepositStatus.CONFIRMED.value,
                        NftDepositStatus.CREDITED.value,
                    ],
                ),
                NftDeposit.block_number > window_floor,
            ),
        )
    ).scalars().all()

    orphaned = 0
    lowest_block: int | None = None
    for deposit in candidates:
        canonical = client.block_hash(deposit.block_number)
        if canonical is None or canonical == deposit.block_hash:
            continue
        if deposit.status == NftDepositStatus.CREDITED.value:
            await _remove_holding(session, deposit)
        deposit.status = NftDepositStatus.ORPHANED.value
        orphaned += 1
        block = deposit.block_number
        lowest_block = block if lowest_block is None else min(lowest_block, block)
    await session.flush()
    return NftReorgReport(orphaned=orphaned, lowest_block=lowest_block)


async def run_scan(  # noqa: PLR0913 - mirrors worker.watcher.run_scan's public shape
    session: AsyncSession,
    client: WatcherClient,
    *,
    confirmations: int,
    reorg_depth: int,
    finality_depth: int = 0,
    start_block: int = 0,
) -> NftScanReport:
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

    recorded = await record_nft_deposits(session, client, from_block=from_block, to_block=head)
    credited = await confirm_and_credit_nfts(session, client, confirmations=confirmations)
    margin = max(reorg_depth, finality_depth)
    reorg = await handle_reorgs(session, client, reorg_depth=confirmations + margin)
    if reorg.lowest_block is not None:
        cursor.last_scanned_block = min(cursor.last_scanned_block, reorg.lowest_block - 1)
        await session.flush()
    return NftScanReport(recorded=recorded, credited=credited, orphaned=reorg.orphaned)
