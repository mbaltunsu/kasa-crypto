from datetime import UTC, datetime, timedelta
from http import HTTPStatus

import pytest

pytest.importorskip("aiosqlite")

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.enums import ErrorCode
from app.models.tables import RateLimitEvent
from app.services.rate_limit import enforce_rate_limit
from tests.support import seed_user


def _enable_rate_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_per_user_cap_returns_429(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_rate_limits(monkeypatch)
    user = await seed_user(session, email="alice@example.com", hd_index=1)
    now = datetime(2026, 6, 9, tzinfo=UTC)

    await enforce_rate_limit(session, action="faucet", user_id=user.id, now=now)

    with pytest.raises(HTTPException) as excinfo:
        await enforce_rate_limit(session, action="faucet", user_id=user.id, now=now)

    assert excinfo.value.status_code == HTTPStatus.TOO_MANY_REQUESTS
    assert excinfo.value.detail["code"] == ErrorCode.RATE_LIMITED.value  # type: ignore[index]
    assert "30 second" in excinfo.value.detail["message"]  # type: ignore[index]


@pytest.mark.asyncio
async def test_global_cap_returns_429_across_two_users(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_rate_limits(monkeypatch)
    alice = await seed_user(session, email="alice@example.com", hd_index=1)
    bob = await seed_user(session, email="bob@example.com", hd_index=2)
    now = datetime(2026, 6, 9, tzinfo=UTC)
    session.add_all(
        [
            RateLimitEvent(
                scope_key=f"user:{alice.id if index % 2 == 0 else bob.id}",
                action="nft_mint",
                created_at=now - timedelta(seconds=1),
            )
            for index in range(20)
        ],
    )
    await session.flush()

    with pytest.raises(HTTPException) as excinfo:
        await enforce_rate_limit(session, action="nft_mint", user_id=alice.id, now=now)

    assert excinfo.value.status_code == HTTPStatus.TOO_MANY_REQUESTS
    assert excinfo.value.detail["code"] == ErrorCode.RATE_LIMITED.value  # type: ignore[index]
    assert "Global rate limit" in excinfo.value.detail["message"]  # type: ignore[index]


@pytest.mark.asyncio
async def test_allowed_again_when_events_fall_outside_window(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_rate_limits(monkeypatch)
    user = await seed_user(session, email="alice@example.com", hd_index=1)
    now = datetime(2026, 6, 9, tzinfo=UTC)
    session.add(
        RateLimitEvent(
            scope_key=f"user:{user.id}",
            action="faucet",
            created_at=now - timedelta(seconds=31),
        ),
    )
    await session.flush()

    await enforce_rate_limit(session, action="faucet", user_id=user.id, now=now)
