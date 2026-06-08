from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.schemas.auth import AccessTokenResponse, AuthResponse, LoginRequest, RefreshRequest, RegisterRequest
from app.schemas.user import UserResponse
from app.services.auth_service import (
    authenticate_user,
    issue_token_pair,
    refresh_access_token,
    register_user,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(
    request: RegisterRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> AuthResponse:
    user = await register_user(session, email=request.email, password=request.password)
    access_token, refresh_token = issue_token_pair(user)
    await session.commit()
    return AuthResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserResponse.model_validate(user),
    )


@router.post("/login", response_model=AuthResponse)
async def login(
    request: LoginRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> AuthResponse:
    user = await authenticate_user(session, email=request.email, password=request.password)
    access_token, refresh_token = issue_token_pair(user)
    return AuthResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserResponse.model_validate(user),
    )


@router.post("/refresh", response_model=AccessTokenResponse)
async def refresh(
    request: RefreshRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> AccessTokenResponse:
    token = await refresh_access_token(session, refresh_token=request.refresh_token)
    return AccessTokenResponse(access_token=token)
