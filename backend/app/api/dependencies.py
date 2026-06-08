from __future__ import annotations

from http import HTTPStatus
from typing import Annotated

from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ErrorCode, UserRole
from app.core.security import verify_token
from app.db import get_db
from app.models.tables import User
from app.services.auth_service import get_user_by_id
from app.services.errors import raise_api_error

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise_api_error(HTTPStatus.UNAUTHORIZED, ErrorCode.UNAUTHORIZED, "Missing bearer token")
    try:
        user_id = verify_token(credentials.credentials, expected_type="access")
    except ValueError:
        raise_api_error(HTTPStatus.UNAUTHORIZED, ErrorCode.UNAUTHORIZED, "Invalid bearer token")

    user = await get_user_by_id(session, user_id)
    if user is None:
        raise_api_error(HTTPStatus.UNAUTHORIZED, ErrorCode.UNAUTHORIZED, "Invalid bearer token")
    return user


async def require_admin(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    if user.role != UserRole.ADMIN.value:
        raise_api_error(HTTPStatus.FORBIDDEN, ErrorCode.UNAUTHORIZED, "Admin access required")
    return user


IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=256)]
