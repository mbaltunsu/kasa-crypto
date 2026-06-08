import asyncio

import pytest

pytest.importorskip("eth_utils")

from kasa_shared.consts import AssetType
from kasa_shared.registry import get_chain

from worker import main as worker_main


def test_start_block_is_min_token_deployment_block() -> None:
    chain = get_chain(11_155_111)
    expected = min(
        asset.deployment_block for asset in chain.assets if asset.type != AssetType.NATIVE
    )
    assert worker_main.start_block(chain) == expected


@pytest.mark.asyncio
async def test_sleep_until_stop_returns_immediately_when_stopped() -> None:
    stop = asyncio.Event()
    stop.set()
    # Must not block for the full 100s when already stopped.
    await asyncio.wait_for(worker_main.sleep_until_stop(stop, 100.0), timeout=1.0)
