from collections.abc import AsyncIterator
from http import HTTPStatus

import pytest

pytest.importorskip("aiosqlite")
pytest.importorskip("pytest_asyncio")
pytest.importorskip("sqlalchemy")

import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.enums import NftHoldingStatus, TransferStatus, UserRole
from app.db import Base
from app.models.tables import NftHolding, NftTransfer, User
from app.services.nft_service import list_holdings, transfer_nft

CONTRACT = "0x88F67A2EbD4C342496d0A477EF58F3a89BCF95F2"
CHAIN_ID = 11_155_111
PASSWORD_HASH = "test-password-hash"  # noqa: S105 - test fixture password hash placeholder.


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    async with factory() as db_session:
        yield db_session
    await engine.dispose()


async def _users(session: AsyncSession) -> tuple[User, User, User]:
    alice = User(
        email="alice@example.com",
        password_hash=PASSWORD_HASH,
        role=UserRole.USER.value,
        hd_index=1,
    )
    bob = User(
        email="bob@example.com",
        password_hash=PASSWORD_HASH,
        role=UserRole.USER.value,
        hd_index=2,
    )
    charlie = User(
        email="charlie@example.com",
        password_hash=PASSWORD_HASH,
        role=UserRole.USER.value,
        hd_index=3,
    )
    session.add_all([alice, bob, charlie])
    await session.flush()
    return alice, bob, charlie


async def _holding(session: AsyncSession, *, user: User, token_id: str) -> NftHolding:
    holding = NftHolding(
        user_id=user.id,
        chain_id=CHAIN_ID,
        contract=CONTRACT,
        token_id=token_id,
        status=NftHoldingStatus.HELD.value,
    )
    session.add(holding)
    await session.flush()
    return holding


@pytest.mark.asyncio
async def test_list_holdings_returns_owned_nfts_with_art(session: AsyncSession) -> None:
    alice, bob, _charlie = await _users(session)
    holding = await _holding(session, user=alice, token_id="1")  # noqa: S106
    await _holding(session, user=bob, token_id="2")  # noqa: S106

    response = await list_holdings(session, user=alice)

    assert len(response) == 1
    assert response[0].id == holding.id
    assert response[0].token_id == "1"  # noqa: S105
    assert response[0].image.startswith("data:image/svg+xml;base64,")
    assert response[0].explorer_url == f"https://sepolia.etherscan.io/address/{CONTRACT}"


@pytest.mark.asyncio
async def test_transfer_reassigns_ownership(session: AsyncSession) -> None:
    alice, bob, _charlie = await _users(session)
    holding = await _holding(session, user=alice, token_id="1")  # noqa: S106

    response = await transfer_nft(
        session,
        sender=alice,
        to_email="bob@example.com",
        nft_id=holding.id,
        idempotency_key="send-1",
    )

    assert response.status == TransferStatus.CONFIRMED
    await session.refresh(holding)
    assert holding.user_id == bob.id
    transfer = (
        await session.execute(select(NftTransfer).where(NftTransfer.id == response.id))
    ).scalar_one()
    assert transfer.nft_holding_id == holding.id
    assert transfer.sender_user_id == alice.id
    assert transfer.recipient_user_id == bob.id


@pytest.mark.asyncio
async def test_transfer_rejects_self_recipient(session: AsyncSession) -> None:
    alice, _bob, _charlie = await _users(session)
    holding = await _holding(session, user=alice, token_id="1")  # noqa: S106

    with pytest.raises(HTTPException) as exc_info:
        await transfer_nft(
            session,
            sender=alice,
            to_email="alice@example.com",
            nft_id=holding.id,
            idempotency_key="send-self",
        )

    assert exc_info.value.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    await session.refresh(holding)
    assert holding.user_id == alice.id


@pytest.mark.asyncio
async def test_transfer_rejects_missing_recipient(session: AsyncSession) -> None:
    alice, _bob, _charlie = await _users(session)
    holding = await _holding(session, user=alice, token_id="1")  # noqa: S106

    with pytest.raises(HTTPException) as exc_info:
        await transfer_nft(
            session,
            sender=alice,
            to_email="nobody@example.com",
            nft_id=holding.id,
            idempotency_key="send-missing",
        )

    assert exc_info.value.status_code == HTTPStatus.NOT_FOUND


@pytest.mark.asyncio
async def test_transfer_is_idempotent_on_replay(session: AsyncSession) -> None:
    alice, bob, _charlie = await _users(session)
    holding = await _holding(session, user=alice, token_id="1")  # noqa: S106

    first = await transfer_nft(
        session,
        sender=alice,
        to_email="bob@example.com",
        nft_id=holding.id,
        idempotency_key="send-replay",
    )
    second = await transfer_nft(
        session,
        sender=alice,
        to_email="bob@example.com",
        nft_id=holding.id,
        idempotency_key="send-replay",
    )

    assert second == first
    await session.refresh(holding)
    assert holding.user_id == bob.id
    transfer_count = (await session.execute(select(func.count(NftTransfer.id)))).scalar_one()
    assert transfer_count == 1


@pytest.mark.asyncio
async def test_transfer_rejects_nft_sender_does_not_own(session: AsyncSession) -> None:
    alice, bob, _charlie = await _users(session)
    holding = await _holding(session, user=bob, token_id="1")  # noqa: S106

    with pytest.raises(HTTPException) as exc_info:
        await transfer_nft(
            session,
            sender=alice,
            to_email="charlie@example.com",
            nft_id=holding.id,
            idempotency_key="send-foreign",
        )

    assert exc_info.value.status_code == HTTPStatus.NOT_FOUND
    await session.refresh(holding)
    assert holding.user_id == bob.id
    transfer_count = (await session.execute(select(func.count(NftTransfer.id)))).scalar_one()
    assert transfer_count == 0
