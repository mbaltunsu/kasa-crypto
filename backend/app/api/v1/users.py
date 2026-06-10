from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.db import get_db
from app.models.tables import User
from app.schemas.user import UserListItem

router = APIRouter(tags=["users"])


@router.get("/users")
async def list_users(
    _user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[UserListItem]:
    """List every user's id + email for the recipient/account pickers.

    Demo-only convenience: gated on authentication, not admin, so regular demo accounts can use the
    transfer picker. A real custodial product would not expose the full directory like this.
    """
    rows = (await session.execute(select(User).order_by(User.email))).scalars().all()
    return [UserListItem.model_validate(row) for row in rows]
