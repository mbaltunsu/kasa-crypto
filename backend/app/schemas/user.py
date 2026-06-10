from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.core.enums import UserRole


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    role: UserRole


class UserListItem(BaseModel):
    """A user as seen by the recipient/account pickers. Demo convenience: any authenticated user
    can list these, which would leak emails in a real custodial product but is intended here."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
