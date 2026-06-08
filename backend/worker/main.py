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
from worker import watcher, withdrawer

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


async def _watcher_loop(ctx: WorkerContext, client: WatcherClient, scan_from: int) -> None:
    while not ctx.stop.is_set():
        try:
            async with ctx.session_factory() as session:
                report = await watcher.run_scan(
                    session,
                    client,
                    confirmations=ctx.settings.deposit_confirmations,
                    reorg_depth=ctx.settings.reorg_depth,
                    finality_depth=ctx.settings.reorg_finality_depth,
                    start_block=scan_from,
                )
                await session.commit()
            if report.recorded or report.credited or report.orphaned:
                logger.info(
                    "watcher chain=%s recorded=%d credited=%d orphaned=%d",
                    client.chain_id,
                    report.recorded,
                    report.credited,
                    report.orphaned,
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
        try:
            client = ChainClient.from_settings(chain.chain_id, settings)
        except KeyError:
            logger.warning("no RPC configured for chain %s; skipping", chain.chain_id)
            continue
        tasks.append(asyncio.create_task(_watcher_loop(ctx, client, start_block(chain))))
        tasks.append(asyncio.create_task(_withdrawer_loop(ctx, client)))

    logger.info("kasa worker started: %d loop(s) across %d chain(s)", len(tasks), len(tasks) // 2)
    await asyncio.gather(*tasks)
    logger.info("kasa worker stopped")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    asyncio.run(run())


if __name__ == "__main__":
    main()
