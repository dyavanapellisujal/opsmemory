"""Authentication service: registration, login, logout, session validation."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from opsmemory.auth.hashing import generate_token, hash_password, hash_token
from opsmemory.auth.providers import AuthProvider, PasswordAuthProvider
from opsmemory.core.errors import OpsMemoryError
from opsmemory.core.logging import get_logger
from opsmemory.db.models import Session, User

logger = get_logger(__name__)


class AuthError(OpsMemoryError):
    """Raised on failed authentication."""

    code = "AUTH_FAILED"
    status_code = 401


class LoginResult:
    """A successful login: the bearer token, its expiry, and the user."""

    def __init__(self, token: str, expires_at: datetime, user: User) -> None:
        self.token = token
        self.expires_at = expires_at
        self.user = user


class AuthService:
    """Manages users and sessions across pluggable auth providers."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        session_ttl_hours: int = 168,
        providers: list[AuthProvider] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._ttl = timedelta(hours=session_ttl_hours)
        self._providers = {p.name: p for p in (providers or [PasswordAuthProvider()])}

    async def ensure_user(
        self, email: str, password: str, *, name: str | None = None, role: str = "engineer"
    ) -> User:
        """Create the user if absent (used for bootstrap and registration)."""
        async with self._session_factory() as session:
            existing = (
                await session.execute(select(User).where(User.email == email))
            ).scalar_one_or_none()
            if existing is not None:
                return existing
            user = User(
                email=email,
                name=name,
                hashed_password=hash_password(password),
                role=role,
            )
            session.add(user)
            await session.commit()
            logger.info("User created email=%s role=%s", email, role)
            return user

    async def login(
        self, email: str, credential: str, *, provider: str = "password"
    ) -> LoginResult:
        """Authenticate and open a session.

        Raises:
            AuthError: If the credential is invalid or the provider unknown.
        """
        auth_provider = self._providers.get(provider)
        if auth_provider is None:
            raise AuthError(f"Unknown auth provider: {provider}")
        async with self._session_factory() as session:
            user = (
                await session.execute(select(User).where(User.email == email))
            ).scalar_one_or_none()
            identity = auth_provider.authenticate(user, credential)
            if identity is None or user is None:
                raise AuthError("Invalid email or password")

            token = generate_token()
            expires_at = _now() + self._ttl
            session.add(
                Session(
                    user_id=user.id,
                    token_hash=hash_token(token),
                    expires_at=expires_at.replace(tzinfo=None),
                )
            )
            await session.commit()
            logger.info("Login email=%s provider=%s", email, provider)
            return LoginResult(token=token, expires_at=expires_at, user=user)

    async def logout(self, token: str) -> None:
        """Revoke the session backing a token (idempotent)."""
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(Session).where(Session.token_hash == hash_token(token))
                )
            ).scalar_one_or_none()
            if row is not None:
                await session.delete(row)
                await session.commit()

    async def authenticate_token(self, token: str) -> User | None:
        """Return the user for a valid, unexpired token, else ``None``."""
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(Session).where(Session.token_hash == hash_token(token))
                )
            ).scalar_one_or_none()
            if row is None:
                return None
            if _aware(row.expires_at) < _now():
                await session.delete(row)
                await session.commit()
                return None
            user = (
                await session.execute(select(User).where(User.id == row.user_id))
            ).scalar_one_or_none()
            return user if user is not None and user.is_active else None

    async def user_count(self) -> int:
        """Number of users (used to decide bootstrap)."""
        async with self._session_factory() as session:
            rows = (await session.execute(select(User.id))).scalars().all()
            return len(rows)

    async def get_user(self, user_id: uuid.UUID) -> User | None:
        """Fetch a user by id."""
        async with self._session_factory() as session:
            return (
                await session.execute(select(User).where(User.id == user_id))
            ).scalar_one_or_none()


def _now() -> datetime:
    """Timezone-aware current UTC time."""
    return datetime.now(UTC)


def _aware(value: datetime) -> datetime:
    """Treat naive DB timestamps as UTC for comparison."""
    return value if value.tzinfo else value.replace(tzinfo=UTC)
