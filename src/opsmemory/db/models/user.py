"""User and session entities for authentication.

Kept deliberately provider-agnostic: ``auth_provider``/``external_id``
identify how a user authenticated so OAuth providers (Google, GitHub,
Microsoft) can be added later without a schema change.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from opsmemory.db.base import Base, PrimaryKeyMixin, TimestampMixin
from opsmemory.db.types import GUID


class User(Base, PrimaryKeyMixin, TimestampMixin):
    """An authenticated platform user."""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(200))
    hashed_password: Mapped[str | None] = mapped_column(String(255))
    auth_provider: Mapped[str] = mapped_column(String(50), default="password")
    external_id: Mapped[str | None] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(50), default="engineer")
    is_active: Mapped[bool] = mapped_column(Boolean(), default=True)

    def __repr__(self) -> str:
        return f"<User {self.email!r} role={self.role}>"


class Session(Base, PrimaryKeyMixin, TimestampMixin):
    """A server-side session backing an opaque bearer token.

    Only the SHA-256 of the token is stored; revocation (logout) deletes the
    row, and expiry is enforced on validation.
    """

    __tablename__ = "sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column()

    user: Mapped[User] = relationship()

    def __repr__(self) -> str:
        return f"<Session user={self.user_id}>"
