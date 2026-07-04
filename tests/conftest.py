"""Shared test fixtures.

Tests run against in-memory SQLite, the keyless hashing embedding provider,
a temporary Kuzu graph, and no LLM (extractive mode) — so the entire suite
needs no network, keys, or services. Migrations are validated against real
PostgreSQL separately (`make migrate`).
"""

import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from opsmemory.ai.providers import HashingEmbeddingProvider
from opsmemory.api.app import create_app, wire_services
from opsmemory.core.config import Environment, Settings
from opsmemory.db.base import Base
from opsmemory.graph.kuzu_store import KuzuGraphStore
from opsmemory.memory.native import NativeMemoryEngine


@pytest.fixture(autouse=True)
def hermetic_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Keep every test hermetic w.r.t. the project ``.env``.

    Importing Cognee (a core dependency) runs ``load_dotenv()``, which leaks
    the project's ``.env`` into ``os.environ``. Since pydantic-settings still
    reads real OS env vars even with ``_env_file=None``, that would make
    ``Settings()`` pick up production values mid-suite depending on import
    order. Strip ``OPSMEMORY_*`` before each test so defaults are honored;
    tests that need env values set them explicitly via ``monkeypatch``.
    """
    for key in [k for k in os.environ if k.startswith("OPSMEMORY_")]:
        monkeypatch.delenv(key, raising=False)
    yield


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Settings for a fully local, keyless test environment."""
    return Settings(
        _env_file=None,
        environment=Environment.TEST,
        database_url="sqlite+aiosqlite:///:memory:",
        graph_db_path=str(tmp_path / "graph"),
        embedding_provider="hashing",
        llm_provider="none",
        memory_engine="native",
        embedding_dimension=64,  # small vectors keep hashing fast in tests
        auth_enabled=False,  # protected routes stay open unless a test opts in
    )


@pytest.fixture
async def engine(settings: Settings) -> AsyncIterator[AsyncEngine]:
    """Async engine with the full schema created."""
    engine = create_async_engine(settings.database_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Session factory bound to the test engine."""
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
async def session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """A database session for direct model tests."""
    async with session_factory() as session:
        yield session


@pytest.fixture
def embeddings(settings: Settings) -> HashingEmbeddingProvider:
    """Deterministic keyless embedding provider."""
    return HashingEmbeddingProvider(dimension=settings.embedding_dimension)


@pytest.fixture
def graph_store(settings: Settings) -> KuzuGraphStore:
    """Embedded Kuzu graph in a temporary directory."""
    return KuzuGraphStore(settings.graph_db_path)


@pytest.fixture
def memory_engine(
    session_factory: async_sessionmaker[AsyncSession],
    embeddings: HashingEmbeddingProvider,
) -> NativeMemoryEngine:
    """Native pgvector/SQLite memory engine."""
    return NativeMemoryEngine(session_factory, embeddings)


@pytest.fixture
def app(
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    graph_store: KuzuGraphStore,
) -> FastAPI:
    """FastAPI app wired to the test database and fakes (lifespan not run)."""
    application = create_app(settings)
    application.state.session_factory = session_factory
    application.state.graph_store = graph_store
    wire_services(application, settings)
    return application


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """HTTP client speaking ASGI directly to the app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
