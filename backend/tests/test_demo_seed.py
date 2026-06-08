import pytest

pytest.importorskip("aiosqlite")
pytest.importorskip("bip_utils")

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.tables import DepositAddress, User
from app.services.auth_service import ensure_demo_user


def _settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    env = {
        "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
        "JWT_SECRET": "test",
        "MASTER_MNEMONIC": "test test test test test test test test test test test junk",
        "RPC_ETHEREUM_SEPOLIA": "http://localhost",
        "RPC_AVALANCHE_FUJI": "http://localhost",
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return Settings()


@pytest.mark.asyncio
async def test_ensure_demo_user_creates_once_and_is_idempotent(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(monkeypatch)

    created_first = await ensure_demo_user(session, settings)
    created_again = await ensure_demo_user(session, settings)

    assert created_first is True
    assert created_again is False

    users = (
        await session.execute(
            select(func.count(User.id)).where(User.email == settings.demo_email),
        )
    ).scalar_one()
    assert users == 1
    # The demo user gets a deposit address like any registered user, so the dashboard works.
    addresses = (await session.execute(select(func.count(DepositAddress.id)))).scalar_one()
    assert addresses == 1
