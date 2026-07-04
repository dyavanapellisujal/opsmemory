"""Tests for system API endpoints (health, ready, stats) and error envelope."""

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import opsmemory
from opsmemory.db.models import Service, Team


async def test_health(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"] == opsmemory.__version__


async def test_ready(client: AsyncClient) -> None:
    response = await client.get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["checks"]["database"] == "ok"


async def test_stats_empty(client: AsyncClient) -> None:
    response = await client.get("/api/v1/stats")
    assert response.status_code == 200
    body = response.json()
    assert body["documents"] == 0
    assert body["services"] == 0


async def test_stats_counts_entities(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    async with session_factory() as session:
        team = Team(name="platform-engineering")
        session.add(team)
        session.add(Service(name="payments-api", owner_team=team))
        session.add(Service(name="redis"))
        await session.commit()

    response = await client.get("/api/v1/stats")
    body = response.json()
    assert body["teams"] == 1
    assert body["services"] == 2


async def test_unknown_route_returns_404(client: AsyncClient) -> None:
    response = await client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
