import pytest

pytest.importorskip("aiosqlite")

from kasa_shared.registry import nfts_of_chain
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.chain.types import Erc721Transfer
from app.core.enums import NftDepositStatus, NftHoldingStatus
from app.models.tables import NftDeposit, NftHolding, User
from tests.support import FakeChainClient, seed_deposit_address, seed_user
from worker import nft_watcher

CHAIN_ID = 11_155_111
ALICE_ADDR = "0x70997970C51812dc3A010C7d01b50e0d17dc79C8"
CONTRACT = nfts_of_chain(CHAIN_ID)[0].address  # registry-derived (survives redeploys)
SENDER = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"
COLLECTIBLE_ID = "42"
LOG_INDEX = 3
ORIGINAL_BLOCK = 100
REMINED_BLOCK = 102
TX_HASH = "0x" + "11" * 32
AA = "0x" + "aa" * 32
BB = "0x" + "bb" * 32
FF = "0x" + "ff" * 32


async def _world(session: AsyncSession) -> User:
    alice = await seed_user(session, email="alice@example.com", hd_index=1)
    await seed_deposit_address(session, user=alice, address=ALICE_ADDR)
    return alice


def _transfer(
    *,
    tx_hash: str = TX_HASH,
    log_index: int = LOG_INDEX,
    block_number: int = ORIGINAL_BLOCK,
    block_hash: str = AA,
    token_id: str = COLLECTIBLE_ID,
) -> Erc721Transfer:
    return Erc721Transfer(
        contract_address=CONTRACT,
        from_address=SENDER,
        to_address=ALICE_ADDR,
        token_id=token_id,
        block_number=block_number,
        block_hash=block_hash,
        tx_hash=tx_hash,
        log_index=log_index,
    )


async def _deposit_count(session: AsyncSession) -> int:
    return int((await session.execute(select(func.count(NftDeposit.id)))).scalar_one())


async def _holding_count(session: AsyncSession) -> int:
    return int((await session.execute(select(func.count(NftHolding.id)))).scalar_one())


@pytest.mark.asyncio
async def test_record_confirm_credit_nft_deposit_and_rescan_is_idempotent(
    session: AsyncSession,
) -> None:
    alice = await _world(session)
    client = FakeChainClient(
        chain_id=CHAIN_ID,
        head=110,
        block_hashes={ORIGINAL_BLOCK: AA},
        erc721_transfers=[_transfer()],
    )

    inserted = await nft_watcher.record_nft_deposits(session, client, from_block=1, to_block=110)
    assert inserted == 1
    deposit = (await session.execute(select(NftDeposit))).scalar_one()
    assert deposit.status == NftDepositStatus.SEEN.value
    assert deposit.user_id == alice.id
    assert deposit.contract == CONTRACT
    assert deposit.token_id == COLLECTIBLE_ID
    assert deposit.log_index == LOG_INDEX

    again = await nft_watcher.record_nft_deposits(session, client, from_block=1, to_block=110)
    assert again == 0
    assert await _deposit_count(session) == 1

    credited = await nft_watcher.confirm_and_credit_nfts(session, client, confirmations=5)
    assert credited == 1
    await session.refresh(deposit)
    assert deposit.status == NftDepositStatus.CREDITED.value

    holding = (await session.execute(select(NftHolding))).scalar_one()
    assert holding.user_id == alice.id
    assert holding.chain_id == CHAIN_ID
    assert holding.contract == CONTRACT
    assert holding.token_id == COLLECTIBLE_ID
    assert holding.status == NftHoldingStatus.HELD.value

    assert await nft_watcher.confirm_and_credit_nfts(session, client, confirmations=5) == 0
    assert await _holding_count(session) == 1


@pytest.mark.asyncio
async def test_reorg_before_credit_orphans_without_holding(session: AsyncSession) -> None:
    await _world(session)
    client = FakeChainClient(
        chain_id=CHAIN_ID,
        head=110,
        block_hashes={ORIGINAL_BLOCK: FF},
        erc721_transfers=[_transfer()],
    )
    assert await nft_watcher.record_nft_deposits(session, client, from_block=1, to_block=110) == 1

    credited = await nft_watcher.confirm_and_credit_nfts(session, client, confirmations=5)
    assert credited == 0
    deposit = (await session.execute(select(NftDeposit))).scalar_one()
    assert deposit.status == NftDepositStatus.ORPHANED.value
    assert await _holding_count(session) == 0


@pytest.mark.asyncio
async def test_reorg_after_credit_removes_holding_and_orphans_deposit(
    session: AsyncSession,
) -> None:
    await _world(session)
    client = FakeChainClient(
        chain_id=CHAIN_ID,
        head=110,
        block_hashes={ORIGINAL_BLOCK: AA},
        erc721_transfers=[_transfer()],
    )
    assert await nft_watcher.record_nft_deposits(session, client, from_block=1, to_block=110) == 1
    assert await nft_watcher.confirm_and_credit_nfts(session, client, confirmations=5) == 1
    assert await _holding_count(session) == 1

    client.block_hashes[ORIGINAL_BLOCK] = FF
    report = await nft_watcher.handle_reorgs(session, client, reorg_depth=50)
    assert report.orphaned == 1
    assert report.lowest_block == ORIGINAL_BLOCK
    deposit = (await session.execute(select(NftDeposit))).scalar_one()
    assert deposit.status == NftDepositStatus.ORPHANED.value
    assert await _holding_count(session) == 0


@pytest.mark.asyncio
async def test_reorg_recovery_remine_recredits_and_bumps_revision(session: AsyncSession) -> None:
    alice = await _world(session)
    client = FakeChainClient(
        chain_id=CHAIN_ID,
        head=110,
        block_hashes={ORIGINAL_BLOCK: AA},
        erc721_transfers=[_transfer()],
    )
    assert await nft_watcher.record_nft_deposits(session, client, from_block=1, to_block=110) == 1
    assert await nft_watcher.confirm_and_credit_nfts(session, client, confirmations=5) == 1

    client.block_hashes[ORIGINAL_BLOCK] = FF
    assert (await nft_watcher.handle_reorgs(session, client, reorg_depth=50)).orphaned == 1
    assert await _holding_count(session) == 0

    client.head = 120
    client.block_hashes[REMINED_BLOCK] = BB
    client.erc721_transfers = [_transfer(block_number=REMINED_BLOCK, block_hash=BB)]
    assert await nft_watcher.record_nft_deposits(session, client, from_block=1, to_block=120) == 1
    deposit = (await session.execute(select(NftDeposit))).scalar_one()
    assert deposit.status == NftDepositStatus.SEEN.value
    assert deposit.block_number == REMINED_BLOCK
    assert deposit.credit_revision == 1

    assert await nft_watcher.confirm_and_credit_nfts(session, client, confirmations=5) == 1
    holding = (await session.execute(select(NftHolding))).scalar_one()
    assert holding.user_id == alice.id
    assert holding.status == NftHoldingStatus.HELD.value
    await session.refresh(deposit)
    assert deposit.status == NftDepositStatus.CREDITED.value
