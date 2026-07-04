"""Authentication tests: hashing, the auth service, and protected routes."""

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from opsmemory.api.app import create_app, wire_services
from opsmemory.auth.hashing import hash_password, verify_password
from opsmemory.auth.service import AuthError, AuthService
from opsmemory.core.config import Environment, Settings
from opsmemory.graph.kuzu_store import KuzuGraphStore


def test_password_hash_roundtrip() -> None:
    stored = hash_password("s3cret")
    assert stored != "s3cret"
    assert verify_password("s3cret", stored)
    assert not verify_password("wrong", stored)
    assert not verify_password("s3cret", "not-a-hash")


async def test_auth_service_login_logout(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    auth = AuthService(session_factory, session_ttl_hours=1)
    await auth.ensure_user("eng@x.io", "pw12345", name="Eng")
    assert await auth.user_count() == 1

    with pytest.raises(AuthError):
        await auth.login("eng@x.io", "wrong")

    result = await auth.login("eng@x.io", "pw12345")
    assert result.user.email == "eng@x.io"
    assert await auth.authenticate_token(result.token) is not None

    await auth.logout(result.token)
    assert await auth.authenticate_token(result.token) is None


@pytest.fixture
def auth_settings(tmp_path) -> Settings:  # type: ignore[no-untyped-def]
    """Settings with authentication enabled."""
    return Settings(
        _env_file=None,
        environment=Environment.TEST,
        database_url="sqlite+aiosqlite:///:memory:",
        graph_db_path=str(tmp_path / "graph-auth"),
        embedding_provider="hashing",
        llm_provider="none",
        embedding_dimension=64,
        auth_enabled=True,
    )


@pytest.fixture
async def auth_client(
    auth_settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    tmp_path,  # type: ignore[no-untyped-def]
) -> AsyncIterator[AsyncClient]:
    """Client for an auth-enabled app with one seeded user."""
    app = create_app(auth_settings)
    app.state.session_factory = session_factory
    app.state.graph_store = KuzuGraphStore(str(tmp_path / "graph-auth"))
    wire_services(app, auth_settings)
    await app.state.auth_service.ensure_user("admin@x.io", "adminpw", role="admin")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def test_protected_route_requires_token(auth_client: AsyncClient) -> None:
    # No token → 401.
    unauth = await auth_client.get("/api/v1/incidents")
    assert unauth.status_code == 401
    assert unauth.json()["error"]["code"] == "UNAUTHORIZED"

    # Login → token.
    login = await auth_client.post(
        "/api/v1/auth/login", json={"email": "admin@x.io", "password": "adminpw"}
    )
    assert login.status_code == 200
    token = login.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    me = await auth_client.get("/api/v1/auth/me", headers=headers)
    assert me.json()["email"] == "admin@x.io"

    # Authenticated request succeeds.
    ok = await auth_client.get("/api/v1/incidents", headers=headers)
    assert ok.status_code == 200

    # Bad credentials → 401.
    bad = await auth_client.post(
        "/api/v1/auth/login", json={"email": "admin@x.io", "password": "nope"}
    )
    assert bad.status_code == 401
