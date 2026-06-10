"""Worker process entrypoint (`python -m worker.main`).

Runs, per chain, a deposit-watcher loop and a withdrawal-processor loop sharing one Postgres — no
broker. Each loop is resilient (a failed pass is logged and retried next tick) and stops cleanly on
SIGINT/SIGTERM. The serializable per-chain business logic lives in `watcher`/`withdrawer`; this
module is only the asyncio scaffolding that schedules them.

Known limitation (acceptable for this single-process demo): `ChainClient` is synchronous, so a slow
RPC call on one chain briefly blocks the shared event loop (and thus the other chains' loops). A
production deployment would run one process per chain, or offload chain I/O via `asyncio.to_thread`,
so chains can't head-of-line-block each other.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
from dataclasses import dataclass
from typing import TYPE_CHECKING

from kasa_shared.consts import AssetType
from kasa_shared.registry import list_chains

from app.chain.client import ChainClient
from app.core.config import Settings, get_settings
from app.core.hd_wallet import hot_wallet_account
from app.db import get_session_factory
from app.models.tables import ChainCursor
from worker import nft_minter, nft_sweeper, nft_watcher, nft_withdrawer, watcher, withdrawer

if TYPE_CHECKING:
    from kasa_shared.models import Chain
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.chain.types import SenderClient, WatcherClient

logger = logging.getLogger("kasa.worker")


@dataclass(frozen=True)
class WorkerContext:
    settings: Settings
    session_factory: async_sessionmaker[AsyncSession]
    stop: asyncio.Event
    hot_wallet_key: str
    hot_wallet_address: str


@dataclass(frozen=True)
class DepositScanReport:
    recorded: int
    credited: int
    orphaned: int
    nft_recorded: int
    nft_credited: int
    nft_orphaned: int


def start_block(chain: Chain) -> int:
    """The earliest block worth scanning: the lowest token deployment block on the chain."""
    token_blocks = [
        asset.deployment_block for asset in chain.assets if asset.type != AssetType.NATIVE
    ]
    return min(token_blocks) if token_blocks else 0


async def sleep_until_stop(stop: asyncio.Event, seconds: float) -> None:
    """Sleep up to `seconds`, returning early the moment a shutdown is requested."""
    with contextlib.suppress(TimeoutError):
        await asyncio.wait_for(stop.wait(), timeout=seconds)


async def _run_deposit_scans(
    session: AsyncSession,
    client: WatcherClient,
    *,
    ctx: WorkerContext,
    start_block: int,
) -> DepositScanReport:
    chain_id = client.chain_id
    head = client.block_number()
    finalized = max(0, head - ctx.settings.deposit_confirmations)

    cursor = await watcher.get_cursor(session, chain_id)
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

    recorded = await watcher.record_deposits(
        session,
        client,
        from_block=from_block,
        to_block=head,
        watch_internal=ctx.settings.watch_internal_transfers,
        hot_wallet_address=ctx.hot_wallet_address,
    )
    nft_recorded = await nft_watcher.record_nft_deposits(
        session,
        client,
        from_block=from_block,
        to_block=head,
    )
    credited = await watcher.confirm_and_credit(
        session,
        client,
        confirmations=ctx.settings.deposit_confirmations,
    )
    nft_credited = await nft_watcher.confirm_and_credit_nfts(
        session,
        client,
        confirmations=ctx.settings.deposit_confirmations,
    )
    margin = max(ctx.settings.reorg_depth, ctx.settings.reorg_finality_depth)
    reorg_depth = ctx.settings.deposit_confirmations + margin
    reorg = await watcher.handle_reorgs(session, client, reorg_depth=reorg_depth)
    nft_reorg = await nft_watcher.handle_reorgs(
        session,
        client,
        reorg_depth=reorg_depth,
    )
    lowest_blocks = [
        block for block in (reorg.lowest_block, nft_reorg.lowest_block) if block is not None
    ]
    if lowest_blocks:
        cursor.last_scanned_block = min(cursor.last_scanned_block, min(lowest_blocks) - 1)
        await session.flush()
    return DepositScanReport(
        recorded=recorded,
        credited=credited,
        orphaned=reorg.orphaned,
        nft_recorded=nft_recorded,
        nft_credited=nft_credited,
        nft_orphaned=nft_reorg.orphaned,
    )


async def _watcher_loop(ctx: WorkerContext, client: WatcherClient, scan_from: int) -> None:
    while not ctx.stop.is_set():
        try:
            async with ctx.session_factory() as session:
                report = await _run_deposit_scans(
                    session,
                    client,
                    ctx=ctx,
                    start_block=scan_from,
                )
                await session.commit()
            if (
                report.recorded
                or report.credited
                or report.orphaned
                or report.nft_recorded
                or report.nft_credited
                or report.nft_orphaned
            ):
                logger.info(
                    "watcher chain=%s recorded=%d credited=%d orphaned=%d "
                    "nft_recorded=%d nft_credited=%d nft_orphaned=%d",
                    client.chain_id,
                    report.recorded,
                    report.credited,
                    report.orphaned,
                    report.nft_recorded,
                    report.nft_credited,
                    report.nft_orphaned,
                )
        except Exception:
            logger.exception("watcher pass failed chain=%s", client.chain_id)
        await sleep_until_stop(ctx.stop, ctx.settings.watcher_poll_seconds)


async def _withdrawer_loop(ctx: WorkerContext, client: SenderClient) -> None:
    while not ctx.stop.is_set():
        try:
            # Three separately-committed phases. Signing persists the nonce + raw tx BEFORE any
            # broadcast, so a crash between phases re-broadcasts the identical signed tx instead of
            # re-signing at a fresh nonce — no double-pay, no stranded nonce (finding #3).
            async with ctx.session_factory() as session:
                await withdrawer.sign_pending(
                    session,
                    client,
                    hot_wallet_key=ctx.hot_wallet_key,
                    hot_wallet_address=ctx.hot_wallet_address,
                )
                await session.commit()
            async with ctx.session_factory() as session:
                broadcast = await withdrawer.broadcast_signed(session, client)
                await session.commit()
            async with ctx.session_factory() as session:
                settled = await withdrawer.confirm_broadcast(
                    session,
                    client,
                    confirmations=ctx.settings.deposit_confirmations,
                    hot_wallet_address=ctx.hot_wallet_address,
                )
                await session.commit()
            if broadcast or settled:
                logger.info(
                    "withdrawer chain=%s broadcast=%d settled=%d",
                    client.chain_id,
                    broadcast,
                    settled,
                )
        except Exception:
            logger.exception("withdrawer pass failed chain=%s", client.chain_id)
        await sleep_until_stop(ctx.stop, ctx.settings.withdrawer_poll_seconds)


async def _nft_minter_loop(ctx: WorkerContext, client: SenderClient) -> None:
    while not ctx.stop.is_set():
        try:
            async with ctx.session_factory() as session:
                await nft_minter.sign_pending_mints(
                    session,
                    client,
                    hot_wallet_key=ctx.hot_wallet_key,
                    hot_wallet_address=ctx.hot_wallet_address,
                )
                await session.commit()
            async with ctx.session_factory() as session:
                broadcast = await nft_minter.broadcast_signed_mints(session, client)
                await session.commit()
            async with ctx.session_factory() as session:
                confirmed = await nft_minter.confirm_mints(
                    session,
                    client,
                    confirmations=ctx.settings.deposit_confirmations,
                    hot_wallet_address=ctx.hot_wallet_address,
                )
                await session.commit()
            if broadcast or confirmed:
                logger.info(
                    "nft-minter chain=%s broadcast=%d confirmed=%d",
                    client.chain_id,
                    broadcast,
                    confirmed,
                )
        except Exception:
            logger.exception("nft minter pass failed chain=%s", client.chain_id)
        await sleep_until_stop(ctx.stop, ctx.settings.withdrawer_poll_seconds)


async def _nft_withdrawer_loop(ctx: WorkerContext, client: SenderClient) -> None:
    while not ctx.stop.is_set():
        try:
            async with ctx.session_factory() as session:
                await nft_withdrawer.sign_pending_withdrawals(
                    session,
                    client,
                    hot_wallet_key=ctx.hot_wallet_key,
                    hot_wallet_address=ctx.hot_wallet_address,
                )
                await session.commit()
            async with ctx.session_factory() as session:
                broadcast = await nft_withdrawer.broadcast_signed_withdrawals(session, client)
                await session.commit()
            async with ctx.session_factory() as session:
                confirmed = await nft_withdrawer.confirm_withdrawals(
                    session,
                    client,
                    confirmations=ctx.settings.deposit_confirmations,
                    hot_wallet_address=ctx.hot_wallet_address,
                )
                await session.commit()
            if broadcast or confirmed:
                logger.info(
                    "nft-withdrawer chain=%s broadcast=%d confirmed=%d",
                    client.chain_id,
                    broadcast,
                    confirmed,
                )
        except Exception:
            logger.exception("nft withdrawer pass failed chain=%s", client.chain_id)
        await sleep_until_stop(ctx.stop, ctx.settings.withdrawer_poll_seconds)


async def _nft_sweeper_loop(ctx: WorkerContext, client: nft_sweeper.SweepClient) -> None:
    while not ctx.stop.is_set():
        try:
            async with ctx.session_factory() as session:
                discovered = await nft_sweeper.discover_sweeps(session, client)
                await session.commit()
            async with ctx.session_factory() as session:
                funded = await nft_sweeper.fund_pending(
                    session,
                    client,
                    hot_wallet_key=ctx.hot_wallet_key,
                    hot_wallet_address=ctx.hot_wallet_address,
                )
                await session.commit()
            async with ctx.session_factory() as session:
                sweeping = await nft_sweeper.sweep_funded(
                    session,
                    client,
                    hot_wallet_address=ctx.hot_wallet_address,
                )
                await session.commit()
            async with ctx.session_factory() as session:
                swept = await nft_sweeper.confirm_sweeps(
                    session,
                    client,
                    confirmations=ctx.settings.deposit_confirmations,
                    hot_wallet_address=ctx.hot_wallet_address,
                )
                await session.commit()
            if discovered or funded or sweeping or swept:
                logger.info(
                    "nft-sweeper chain=%s discovered=%d funded=%d sweeping=%d swept=%d",
                    client.chain_id,
                    discovered,
                    funded,
                    sweeping,
                    swept,
                )
        except Exception:
            logger.exception("nft sweeper pass failed chain=%s", client.chain_id)
        await sleep_until_stop(ctx.stop, ctx.settings.withdrawer_poll_seconds)


def _install_signal_handlers(stop: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)


async def run() -> None:
    settings = get_settings()
    hot_wallet = hot_wallet_account(settings.master_mnemonic)
    ctx = WorkerContext(
        settings=settings,
        session_factory=get_session_factory(),
        stop=asyncio.Event(),
        hot_wallet_key=hot_wallet.private_key,
        hot_wallet_address=hot_wallet.address,
    )
    _install_signal_handlers(ctx.stop)

    tasks: list[asyncio.Task[None]] = []
    for chain in list_chains():
        if not settings.is_chain_enabled(chain.chain_id):
            logger.info("chain %s disabled by config; skipping", chain.chain_id)
            continue
        try:
            client = ChainClient.from_settings(chain.chain_id, settings)
        except (KeyError, ValueError):
            # KeyError: chain absent from the RPC field map. ValueError: known chain but its RPC
            # URL list resolved empty (e.g. RPC_HARDHAT="" on a testnet run). Either way the chain
            # has no reachable endpoint — skip it rather than crash every other chain's loops.
            logger.warning("no RPC configured for chain %s; skipping", chain.chain_id)
            continue
        tasks.append(asyncio.create_task(_watcher_loop(ctx, client, start_block(chain))))
        tasks.append(asyncio.create_task(_withdrawer_loop(ctx, client)))
        tasks.append(asyncio.create_task(_nft_minter_loop(ctx, client)))
        tasks.append(asyncio.create_task(_nft_withdrawer_loop(ctx, client)))
        tasks.append(asyncio.create_task(_nft_sweeper_loop(ctx, client)))

    logger.info("kasa worker started: %d loop(s) across %d chain(s)", len(tasks), len(tasks) // 5)
    await asyncio.gather(*tasks)
    logger.info("kasa worker stopped")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    asyncio.run(run())


if __name__ == "__main__":
    main()
