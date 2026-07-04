"""Authentication request/response schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """Credentials for password login."""

    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=200)


class LoginResponse(BaseModel):
    """A successful login: bearer token + the authenticated user."""

    token: str
    expires_at: datetime
    user: "UserOut"


class UserOut(BaseModel):
    """A user profile."""

    id: uuid.UUID
    email: str
    name: str | None
    role: str

    model_config = {"from_attributes": True}
