from datetime import UTC, datetime, timedelta
from typing import Any, Literal, TypedDict, cast
from uuid import UUID

from app.core.config import Settings, get_settings

TokenType = Literal["access", "refresh"]
ALGORITHM = "HS256"


class TokenClaims(TypedDict):
    sub: str
    typ: TokenType
    exp: int
    iat: int


def hash_password(password: str) -> str:
    from passlib.context import CryptContext

    context = CryptContext(schemes=["argon2"], deprecated="auto")
    return cast(str, context.hash(password))


def verify_password(password: str, password_hash: str) -> bool:
    from passlib.context import CryptContext

    context = CryptContext(schemes=["argon2"], deprecated="auto")
    return cast(bool, context.verify(password, password_hash))


def _claims(subject: UUID, token_type: TokenType, ttl_seconds: int) -> TokenClaims:
    now = datetime.now(UTC)
    expires_at = now + timedelta(seconds=ttl_seconds)
    return {
        "sub": str(subject),
        "typ": token_type,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }


def create_token(
    *,
    subject: UUID,
    token_type: TokenType,
    settings: Settings | None = None,
) -> str:
    from jose import jwt

    resolved = settings or get_settings()
    ttl = (
        resolved.access_ttl_seconds
        if token_type == "access"
        else resolved.refresh_ttl_seconds
    )
    return cast(
        str,
        jwt.encode(_claims(subject, token_type, ttl), resolved.jwt_secret, algorithm=ALGORITHM),
    )


def create_access_token(subject: UUID, settings: Settings | None = None) -> str:
    return create_token(subject=subject, token_type="access", settings=settings)


def create_refresh_token(subject: UUID, settings: Settings | None = None) -> str:
    return create_token(subject=subject, token_type="refresh", settings=settings)


def verify_token(
    token: str,
    *,
    expected_type: TokenType,
    settings: Settings | None = None,
) -> UUID:
    from jose import JWTError, jwt

    resolved = settings or get_settings()
    try:
        raw_claims: dict[str, Any] = jwt.decode(
            token,
            resolved.jwt_secret,
            algorithms=[ALGORITHM],
        )
    except JWTError as exc:
        msg = "invalid token"
        raise ValueError(msg) from exc

    token_type = raw_claims.get("typ")
    subject = raw_claims.get("sub")
    if token_type != expected_type or not isinstance(subject, str):
        msg = "invalid token"
        raise ValueError(msg)
    try:
        return UUID(subject)
    except ValueError as exc:
        msg = "invalid token subject"
        raise ValueError(msg) from exc
