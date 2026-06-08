import uuid

import pytest

pytest.importorskip("jose")
pytest.importorskip("passlib")

from app.core.config import Settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
    verify_token,
)


def _settings() -> Settings:
    return Settings(
        DATABASE_URL="sqlite+aiosqlite:///:memory:",
        JWT_SECRET="test-secret",
        MASTER_MNEMONIC="test test test test test test test test test test test junk",
        RPC_ETHEREUM_SEPOLIA="http://localhost",
        RPC_AVALANCHE_FUJI="http://localhost",
    )


def test_password_hash_and_verify() -> None:
    password_hash = hash_password("correct horse battery staple")

    assert password_hash != "correct horse battery staple"
    assert verify_password("correct horse battery staple", password_hash)
    assert not verify_password("wrong", password_hash)


def test_jwt_access_and_refresh_roundtrip() -> None:
    settings = _settings()
    subject = uuid.uuid4()

    access_token = create_access_token(subject, settings=settings)
    refresh_token = create_refresh_token(subject, settings=settings)

    assert verify_token(access_token, expected_type="access", settings=settings) == subject
    assert verify_token(refresh_token, expected_type="refresh", settings=settings) == subject
    with pytest.raises(ValueError):
        verify_token(access_token, expected_type="refresh", settings=settings)
