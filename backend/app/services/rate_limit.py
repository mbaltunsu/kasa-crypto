from __future__ import annotations

from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from typing import TYPE_CHECKING

from sqlalchemy import delete, func, select

from app.core.config import get_settings
from app.core.enums import ErrorCode
from app.models.tables import RateLimitEvent
from app.services.errors import raise_api_error

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession

type WindowLimit = tuple[int, int]
type ActionLimits = dict[str, list[WindowLimit]]

LIMITS: dict[str, ActionLimits] = {
    "faucet": {
        "per_user": [(30, 1), (3_600, 5), (86_400, 15)],
        "global": [(3_600, 40), (86_400, 200)],
    },
    "withdrawal": {
        "per_user": [(30, 1), (3_600, 10), (86_400, 30)],
        "global": [(3_600, 60), (86_400, 300)],
    },
    "nft_withdrawal": {
        "per_user": [(30, 1), (3_600, 10), (86_400, 30)],
        "global": [(3_600, 60), (86_400, 300)],
    },
    "nft_mint": {
        "per_user": [],
        "global": [(3_600, 20), (86_400, 100)],
    },
}


def _window_name(window_seconds: int) -> str:
    if window_seconds % 86_400 == 0:
        return f"{window_seconds // 86_400} day"
    if window_seconds % 3_600 == 0:
        return f"{window_seconds // 3_600} hour"
    if window_seconds % 60 == 0:
        return f"{window_seconds // 60} minute"
    return f"{window_seconds} second"


async def _count_events(
    session: AsyncSession,
    *,
    action: str,
    since: datetime,
    scope_key: str | None = None,
) -> int:
    statement = select(func.count()).select_from(RateLimitEvent).where(
        RateLimitEvent.action == action,
        RateLimitEvent.created_at >= since,
    )
    if scope_key is not None:
        statement = statement.where(RateLimitEvent.scope_key == scope_key)
    return int((await session.execute(statement)).scalar_one())


async def enforce_rate_limit(
    session: AsyncSession,
    *,
    action: str,
    user_id: UUID,
    now: datetime | None = None,
) -> None:
    if not get_settings().rate_limit_enabled:
        return

    limits = LIMITS.get(action)
    if limits is None:
        return

    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    scope_key = f"user:{user_id}"

    for window_seconds, limit in limits["per_user"]:
        count = await _count_events(
            session,
            action=action,
            since=current - timedelta(seconds=window_seconds),
            scope_key=scope_key,
        )
        if count >= limit:
            raise_api_error(
                HTTPStatus.TOO_MANY_REQUESTS,
                ErrorCode.RATE_LIMITED,
                f"Rate limit exceeded for {action}: max {limit} per {_window_name(window_seconds)}",
            )

    for window_seconds, limit in limits["global"]:
        count = await _count_events(
            session,
            action=action,
            since=current - timedelta(seconds=window_seconds),
        )
        if count >= limit:
            raise_api_error(
                HTTPStatus.TOO_MANY_REQUESTS,
                ErrorCode.RATE_LIMITED,
                f"Global rate limit exceeded for {action}: max {limit} per "
                f"{_window_name(window_seconds)}",
            )

    session.add(RateLimitEvent(scope_key=scope_key, action=action, created_at=current))
    await session.flush()

    windows = [window for window, _limit in limits["per_user"] + limits["global"]]
    if windows:
        await session.execute(
            delete(RateLimitEvent).where(
                RateLimitEvent.action == action,
                RateLimitEvent.created_at < current - timedelta(seconds=max(windows)),
            ),
        )
