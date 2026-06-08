from __future__ import annotations

from http import HTTPStatus
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.enums import ErrorCode, UserRole
from app.core.hd_wallet import derive_deposit_address
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
    verify_token,
)
from app.models.tables import DepositAddress, User
from app.services.errors import raise_api_error
from kasa_shared.registry import list_chains


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _primary_chain_id() -> int:
    return list_chains()[0].chain_id


async def _next_hd_index(session: AsyncSession) -> int:
    statement = select(func.coalesce(func.max(User.hd_index), 0))
    current = int((await session.execute(statement)).scalar_one())
    return max(1, current + 1)


async def register_user(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    settings: Settings | None = None,
) -> User:
    resolved_settings = settings or get_settings()
    normalized_email = _normalize_email(email)
    existing = (
        await session.execute(select(User).where(User.email == normalized_email))
    ).scalar_one_or_none()
    if existing is not None:
        raise_api_error(HTTPStatus.CONFLICT, ErrorCode.VALIDATION_ERROR, "Email is already registered")

    hd_index = await _next_hd_index(session)
    chain_id = _primary_chain_id()
    derived = derive_deposit_address(
        resolved_settings.master_mnemonic,
        chain_id=chain_id,
        hd_index=hd_index,
    )
    user = User(
        email=normalized_email,
        password_hash=hash_password(password),
        role=UserRole.USER.value,
        hd_index=hd_index,
    )
    session.add(user)
    await session.flush()
    session.add(
        DepositAddress(
            user_id=user.id,
            address=derived.address,
            derivation_path=derived.derivation_path,
        ),
    )
    try:
        await session.flush()
    except IntegrityError:
        raise_api_error(
            HTTPStatus.CONFLICT,
            ErrorCode.VALIDATION_ERROR,
            "Email or deposit address is already registered",
        )
    return user


async def authenticate_user(session: AsyncSession, *, email: str, password: str) -> User:
    normalized_email = _normalize_email(email)
    user = (
        await session.execute(select(User).where(User.email == normalized_email))
    ).scalar_one_or_none()
    if user is None or not verify_password(password, user.password_hash):
        raise_api_error(HTTPStatus.UNAUTHORIZED, ErrorCode.UNAUTHORIZED, "Invalid email or password")
    return user


async def get_user_by_id(session: AsyncSession, user_id: UUID) -> User | None:
    return (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()


def issue_token_pair(user: User, settings: Settings | None = None) -> tuple[str, str]:
    return (
        create_access_token(user.id, settings=settings),
        create_refresh_token(user.id, settings=settings),
    )


async def refresh_access_token(
    session: AsyncSession,
    *,
    refresh_token: str,
    settings: Settings | None = None,
) -> str:
    try:
        user_id = verify_token(refresh_token, expected_type="refresh", settings=settings)
    except ValueError:
        raise_api_error(HTTPStatus.UNAUTHORIZED, ErrorCode.UNAUTHORIZED, "Invalid refresh token")

    user = await get_user_by_id(session, user_id)
    if user is None:
        raise_api_error(HTTPStatus.UNAUTHORIZED, ErrorCode.UNAUTHORIZED, "Invalid refresh token")
    return create_access_token(user.id, settings=settings)
