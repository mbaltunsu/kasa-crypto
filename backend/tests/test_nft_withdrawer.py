import pytest

pytest.importorskip("aiosqlite")

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.chain.types import TxReceipt
from app.core.enums import NftHoldingStatus, NftWithdrawalStatus
from app.models.tables import HotWalletNonce, NftHolding, NftWithdrawalRequest
from app.services.nft_service import request_withdrawal
from tests.support import FakeChainClient, seed_user
from worker import nft_withdrawer

CHAIN_ID = 11_155_111
HOT_ADDR = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"
HOT_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
EXTERNAL = "0x70997970C51812dc3A010C7d01b50e0d17dc79C8"
CONTRACT = "0x88F67A2EbD4C342496d0A477EF58F3a89BCF95F2"
TOKEN_ID = "42"  # noqa: S105
FIRST_NONCE = 7
NEXT_NONCE = 8


async def _holding(session: AsyncSession) -> NftHolding:
    user = await seed_user(session, email="a@example.com", hd_index=1)
    holding = NftHolding(
        user_id=user.id,
        chain_id=CHAIN_ID,
        contract=CONTRACT,
        token_id=TOKEN_ID,
        status=NftHoldingStatus.HELD.value,
    )
    session.add(holding)
    await session.flush()
    await request_withdrawal(
        session,
        user=user,
        nft_id=holding.id,
        to_address=EXTERNAL,
        idempotency_key="nft-wd",
    )
    await session.refresh(holding)
    return holding


async def _request(session: AsyncSession) -> NftWithdrawalRequest:
    return (await session.execute(select(NftWithdrawalRequest))).scalar_one()


@pytest.mark.asyncio
async def test_sign_broadcast_confirm_sets_holding_withdrawn(
    session: AsyncSession,
) -> None:
    holding = await _holding(session)
    client = FakeChainClient(chain_id=CHAIN_ID, nonces={HOT_ADDR.lower(): FIRST_NONCE})

    broadcast = await nft_withdrawer.broadcast_pending_withdrawals(
        session,
        client,
        hot_wallet_key=HOT_KEY,
        hot_wallet_address=HOT_ADDR,
    )
    assert broadcast == 1
    request = await _request(session)
    assert request.status == NftWithdrawalStatus.BROADCAST.value
    assert request.nonce == FIRST_NONCE
    assert request.tx_hash is not None
    assert client.sent[0].kind == "erc721_transfer"
    assert client.sent[0].token_address == CONTRACT
    assert client.sent[0].to_address == EXTERNAL
    assert client.sent[0].value == int(TOKEN_ID)
    nonce = (
        await session.execute(select(HotWalletNonce).where(HotWalletNonce.chain_id == CHAIN_ID))
    ).scalar_one()
    assert nonce.next_nonce == NEXT_NONCE

    block_hash = "0x" + "ab" * 32
    client.receipts[request.tx_hash] = TxReceipt(
        tx_hash=request.tx_hash,
        status=1,
        block_number=10,
        block_hash=block_hash,
    )
    client.head = 100
    client.block_hashes[10] = block_hash

    confirmed = await nft_withdrawer.confirm_withdrawals(
        session,
        client,
        confirmations=5,
        hot_wallet_address=HOT_ADDR,
    )
    assert confirmed == 1
    await session.refresh(request)
    await session.refresh(holding)
    assert request.status == NftWithdrawalStatus.CONFIRMED.value
    assert holding.status == NftHoldingStatus.WITHDRAWN.value


@pytest.mark.asyncio
async def test_reverted_receipt_fails_and_releases_holding(session: AsyncSession) -> None:
    holding = await _holding(session)
    client = FakeChainClient(chain_id=CHAIN_ID, nonces={HOT_ADDR.lower(): 0})
    await nft_withdrawer.broadcast_pending_withdrawals(
        session,
        client,
        hot_wallet_key=HOT_KEY,
        hot_wallet_address=HOT_ADDR,
    )
    request = await _request(session)
    assert request.tx_hash is not None
    block_hash = "0x" + "ab" * 32
    client.receipts[request.tx_hash] = TxReceipt(
        tx_hash=request.tx_hash,
        status=0,
        block_number=10,
        block_hash=block_hash,
    )
    client.head = 100
    client.block_hashes[10] = block_hash

    confirmed = await nft_withdrawer.confirm_withdrawals(
        session,
        client,
        confirmations=5,
        hot_wallet_address=HOT_ADDR,
    )

    assert confirmed == 0
    await session.refresh(request)
    await session.refresh(holding)
    assert request.status == NftWithdrawalStatus.FAILED.value
    assert request.error == "transaction reverted on-chain"
    assert holding.status == NftHoldingStatus.HELD.value


@pytest.mark.asyncio
async def test_dropped_superseded_nonce_fails_and_releases_holding(
    session: AsyncSession,
) -> None:
    holding = await _holding(session)
    client = FakeChainClient(chain_id=CHAIN_ID, nonces={HOT_ADDR.lower(): 0})
    await nft_withdrawer.broadcast_pending_withdrawals(
        session,
        client,
        hot_wallet_key=HOT_KEY,
        hot_wallet_address=HOT_ADDR,
    )
    request = await _request(session)
    client.latest_nonces[HOT_ADDR.lower()] = 1

    confirmed = await nft_withdrawer.confirm_withdrawals(
        session,
        client,
        confirmations=5,
        hot_wallet_address=HOT_ADDR,
    )

    assert confirmed == 0
    await session.refresh(request)
    await session.refresh(holding)
    assert request.status == NftWithdrawalStatus.FAILED.value
    assert request.error == "transaction dropped (nonce superseded)"
    assert holding.status == NftHoldingStatus.HELD.value
