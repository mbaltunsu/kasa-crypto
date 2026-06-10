import uuid

import pytest

pytest.importorskip("aiosqlite")

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.chain.client import ERC20_TRANSFER_TOPIC, ZERO_TOPIC, address_to_topic
from app.chain.types import TxLog, TxReceipt
from app.core.enums import LedgerEntryType, NftHoldingStatus, NftMintStatus, WithdrawalStatus
from app.models.tables import (
    Asset,
    HotWalletNonce,
    NftHolding,
    NftMintRequest,
    User,
    WithdrawalRequest,
)
from app.services import ledger
from app.services.withdrawal_service import create_withdrawal
from tests.support import FakeChainClient, seed_asset, seed_deposit_address, seed_user
from worker import nft_minter, withdrawer

CHAIN_ID = 11_155_111
HOT_ADDR = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"
HOT_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
USER_ADDR = "0x70997970C51812dc3A010C7d01b50e0d17dc79C8"
EXTERNAL = "0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC"
CONTRACT = "0x88F67A2EbD4C342496d0A477EF58F3a89BCF95F2"
ONE_ETH = 500_000_000_000_000
FIRST_MINT_NONCE = 7
MINT_TOKEN_ID = 42
MINTED_ID_TEXT = "42"
SHARED_START_NONCE = 11
SHARED_WITHDRAWAL_NONCE = 12
SHARED_NEXT_NONCE = 13


async def _mint_request(session: AsyncSession, user: User) -> NftMintRequest:
    request = NftMintRequest(
        user_id=user.id,
        chain_id=CHAIN_ID,
        contract=CONTRACT,
        to_address=USER_ADDR,
        status=NftMintStatus.REQUESTED.value,
    )
    session.add(request)
    await session.flush()
    return request


def _mint_receipt(
    tx_hash: str,
    *,
    token_id: int,
    status: int = 1,
    block_number: int = 10,
) -> TxReceipt:
    block_hash = "0x" + "ab" * 32
    token_topic = "0x" + f"{token_id:064x}"
    return TxReceipt(
        tx_hash=tx_hash,
        status=status,
        block_number=block_number,
        block_hash=block_hash,
        logs=(
            TxLog(
                address=CONTRACT,
                topics=(
                    ERC20_TRANSFER_TOPIC,
                    ZERO_TOPIC,
                    address_to_topic(USER_ADDR),
                    token_topic,
                ),
                data="0x",
                log_index=0,
            ),
        ),
    )


async def _fund_wallet(session: AsyncSession, user: User, asset: Asset, amount: int) -> None:
    source = await ledger.get_or_create_account(
        session, asset=asset, name="test_source", owner_type="system",
    )
    wallet = await ledger.get_user_wallet_account(session, user=user, asset=asset)
    await ledger.post(
        session,
        transaction_type=LedgerEntryType.DEPOSIT,
        idempotency_key=f"fund:{user.id}:{asset.id}",
        ref_type="test",
        ref_id="fund",
        legs=[ledger.LedgerLeg(source, asset, -amount), ledger.LedgerLeg(wallet, asset, amount)],
    )


@pytest.mark.asyncio
async def test_mint_sign_broadcast_confirm_writes_holding(session: AsyncSession) -> None:
    user = await seed_user(session, email="a@example.com", hd_index=1)
    request = await _mint_request(session, user)

    client = FakeChainClient(chain_id=CHAIN_ID, nonces={HOT_ADDR.lower(): FIRST_MINT_NONCE})
    sent = await nft_minter.broadcast_pending_mints(
        session, client, hot_wallet_key=HOT_KEY, hot_wallet_address=HOT_ADDR,
    )
    assert sent == 1
    await session.refresh(request)
    assert request.status == NftMintStatus.BROADCAST.value
    assert request.nonce == FIRST_MINT_NONCE
    assert request.tx_hash is not None
    assert client.sent[0].kind == "erc721_mint"
    assert client.sent[0].token_address == CONTRACT
    assert client.sent[0].to_address == USER_ADDR

    client.receipts[request.tx_hash] = _mint_receipt(request.tx_hash, token_id=MINT_TOKEN_ID)
    client.head = 100
    client.block_hashes[10] = "0x" + "ab" * 32

    confirmed = await nft_minter.confirm_mints(
        session, client, confirmations=5, hot_wallet_address=HOT_ADDR,
    )
    assert confirmed == 1
    await session.refresh(request)
    assert request.status == NftMintStatus.CONFIRMED.value
    assert request.token_id == MINTED_ID_TEXT
    holding = (
        await session.execute(select(NftHolding).where(NftHolding.token_id == MINTED_ID_TEXT))
    ).scalar_one()
    assert holding.user_id == user.id
    assert holding.contract == CONTRACT
    assert holding.status == NftHoldingStatus.HELD.value


@pytest.mark.asyncio
async def test_mint_reverted_receipt_fails_request(session: AsyncSession) -> None:
    user = await seed_user(session, email="a@example.com", hd_index=1)
    request = await _mint_request(session, user)
    client = FakeChainClient(chain_id=CHAIN_ID, nonces={HOT_ADDR.lower(): 0})
    await nft_minter.broadcast_pending_mints(
        session, client, hot_wallet_key=HOT_KEY, hot_wallet_address=HOT_ADDR,
    )
    await session.refresh(request)
    assert request.tx_hash is not None
    client.receipts[request.tx_hash] = _mint_receipt(
        request.tx_hash, token_id=MINT_TOKEN_ID, status=0,
    )
    client.head = 100
    client.block_hashes[10] = "0x" + "ab" * 32

    confirmed = await nft_minter.confirm_mints(
        session, client, confirmations=5, hot_wallet_address=HOT_ADDR,
    )
    assert confirmed == 0
    await session.refresh(request)
    assert request.status == NftMintStatus.FAILED.value
    assert request.error == "transaction reverted on-chain"
    assert (await session.execute(select(NftHolding))).first() is None


@pytest.mark.asyncio
async def test_mint_dropped_superseded_nonce_fails_request(session: AsyncSession) -> None:
    user = await seed_user(session, email="a@example.com", hd_index=1)
    request = await _mint_request(session, user)
    client = FakeChainClient(chain_id=CHAIN_ID, nonces={HOT_ADDR.lower(): 0})
    await nft_minter.broadcast_pending_mints(
        session, client, hot_wallet_key=HOT_KEY, hot_wallet_address=HOT_ADDR,
    )
    client.latest_nonces[HOT_ADDR.lower()] = 1
    first_unmined_head = 20
    client.head = first_unmined_head

    confirmed = await nft_minter.confirm_mints(
        session, client, confirmations=5, hot_wallet_address=HOT_ADDR,
    )
    assert confirmed == 0
    await session.refresh(request)
    assert request.status == NftMintStatus.BROADCAST.value
    assert request.unmined_since_block == first_unmined_head

    client.head = 25
    confirmed = await nft_minter.confirm_mints(
        session, client, confirmations=5, hot_wallet_address=HOT_ADDR,
    )
    assert confirmed == 0
    await session.refresh(request)
    assert request.status == NftMintStatus.FAILED.value
    assert request.error == "transaction dropped (nonce superseded)"


@pytest.mark.asyncio
async def test_lagging_receipt_after_mined_mint_is_not_failed(
    session: AsyncSession,
) -> None:
    user = await seed_user(session, email="a@example.com", hd_index=1)
    request = await _mint_request(session, user)
    client = FakeChainClient(chain_id=CHAIN_ID, nonces={HOT_ADDR.lower(): 0})
    await nft_minter.broadcast_pending_mints(
        session,
        client,
        hot_wallet_key=HOT_KEY,
        hot_wallet_address=HOT_ADDR,
    )
    await session.refresh(request)
    assert request.tx_hash is not None
    client.latest_nonces[HOT_ADDR.lower()] = 1
    first_unmined_head = 30
    client.head = first_unmined_head

    confirmed = await nft_minter.confirm_mints(
        session,
        client,
        confirmations=5,
        hot_wallet_address=HOT_ADDR,
    )

    assert confirmed == 0
    await session.refresh(request)
    assert request.status == NftMintStatus.BROADCAST.value
    assert request.unmined_since_block == first_unmined_head

    block_hash = "0x" + "ab" * 32
    client.receipts[request.tx_hash] = _mint_receipt(
        request.tx_hash,
        token_id=MINT_TOKEN_ID,
        block_number=31,
    )
    client.head = 40
    client.block_hashes[31] = block_hash

    confirmed = await nft_minter.confirm_mints(
        session,
        client,
        confirmations=5,
        hot_wallet_address=HOT_ADDR,
    )

    assert confirmed == 1
    await session.refresh(request)
    assert request.status == NftMintStatus.CONFIRMED.value
    assert request.token_id == MINTED_ID_TEXT
    cleared_marker: int | None = request.unmined_since_block
    assert cleared_marker is None
    holding = (
        await session.execute(select(NftHolding).where(NftHolding.token_id == MINTED_ID_TEXT))
    ).scalar_one()
    assert holding.user_id == user.id
    assert holding.contract == CONTRACT
    assert holding.status == NftHoldingStatus.HELD.value


@pytest.mark.asyncio
async def test_dropped_mint_fails_after_unmined_grace_window(session: AsyncSession) -> None:
    user = await seed_user(session, email="a@example.com", hd_index=1)
    request = await _mint_request(session, user)
    client = FakeChainClient(chain_id=CHAIN_ID, nonces={HOT_ADDR.lower(): 0})
    await nft_minter.broadcast_pending_mints(
        session,
        client,
        hot_wallet_key=HOT_KEY,
        hot_wallet_address=HOT_ADDR,
    )
    client.latest_nonces[HOT_ADDR.lower()] = 1
    first_unmined_head = 50
    client.head = first_unmined_head

    confirmed = await nft_minter.confirm_mints(
        session,
        client,
        confirmations=6,
        hot_wallet_address=HOT_ADDR,
    )

    assert confirmed == 0
    await session.refresh(request)
    assert request.status == NftMintStatus.BROADCAST.value
    assert request.unmined_since_block == first_unmined_head

    client.head = 56
    confirmed = await nft_minter.confirm_mints(
        session,
        client,
        confirmations=6,
        hot_wallet_address=HOT_ADDR,
    )

    assert confirmed == 0
    await session.refresh(request)
    assert request.status == NftMintStatus.FAILED.value
    assert request.error == "transaction dropped (nonce superseded)"


@pytest.mark.asyncio
async def test_mint_and_withdrawal_share_hot_wallet_nonce_row(session: AsyncSession) -> None:
    user = await seed_user(session, email="a@example.com", hd_index=1)
    await seed_deposit_address(session, user=user, address=USER_ADDR)
    await _mint_request(session, user)
    asset = await seed_asset(
        session, chain_id=CHAIN_ID, asset_type="native", symbol="ETH", decimals=18,
    )
    await _fund_wallet(session, user, asset, 2 * ONE_ETH)
    response = await create_withdrawal(
        session,
        user=user,
        asset_id=asset.id,
        to_address=EXTERNAL,
        amount=ONE_ETH,
        idempotency_key=f"wd:{uuid.uuid4()}",
    )

    client = FakeChainClient(chain_id=CHAIN_ID, nonces={HOT_ADDR.lower(): SHARED_START_NONCE})
    assert await nft_minter.sign_pending_mints(
        session, client, hot_wallet_key=HOT_KEY, hot_wallet_address=HOT_ADDR,
    ) == 1
    assert await withdrawer.sign_pending(
        session, client, hot_wallet_key=HOT_KEY, hot_wallet_address=HOT_ADDR,
    ) == 1

    mint_request = (await session.execute(select(NftMintRequest))).scalar_one()
    withdrawal_request = (
        await session.execute(select(WithdrawalRequest).where(WithdrawalRequest.id == response.id))
    ).scalar_one()
    assert mint_request.nonce == SHARED_START_NONCE
    assert withdrawal_request.nonce == SHARED_WITHDRAWAL_NONCE
    assert mint_request.status == NftMintStatus.SIGNING.value
    assert withdrawal_request.status == WithdrawalStatus.SIGNING.value
    nonce_row = (
        await session.execute(select(HotWalletNonce).where(HotWalletNonce.chain_id == CHAIN_ID))
    ).scalar_one()
    assert nonce_row.next_nonce == SHARED_NEXT_NONCE
