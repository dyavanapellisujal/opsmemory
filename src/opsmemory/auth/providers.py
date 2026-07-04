"""Authentication providers.

An :class:`AuthProvider` verifies a credential and returns the identity of
the authenticated user. The MVP ships :class:`PasswordAuthProvider`; OAuth
providers implement the same protocol and are registered by name.
"""

from typing import Protocol

from pydantic import BaseModel

from opsmemory.auth.hashing import verify_password
from opsmemory.db.models import User


class Identity(BaseModel):
    """The outcome of a successful authentication."""

    email: str
    name: str | None = None
    provider: str = "password"
    external_id: str | None = None


class AuthProvider(Protocol):
    """Verifies a credential for a known user and yields their identity."""

    name: str

    def authenticate(self, user: User | None, credential: str) -> Identity | None:
        """Return an :class:`Identity` if the credential is valid, else ``None``."""
        ...


class PasswordAuthProvider:
    """Username/password authentication against the stored PBKDF2 hash."""

    name = "password"

    def authenticate(self, user: User | None, credential: str) -> Identity | None:
        """Validate the password against the user's stored hash."""
        if user is None or not user.is_active or not user.hashed_password:
            return None
        if not verify_password(credential, user.hashed_password):
            return None
        return Identity(
            email=user.email, name=user.name, provider=self.name, external_id=user.external_id
        )
