"""End-to-end API tests: connectors → ingestion → search → chat → teaching."""

import asyncio
from pathlib import Path

from httpx import AsyncClient


async def _register_local_connector(client: AsyncClient, tmp_path: Path) -> str:
    (tmp_path / "docs").mkdir(exist_ok=True)
    (tmp_path / "docs" / "runbook.md").write_text(
        "# Redis Recovery Runbook\n\n"
        "payments-api depends on redis.\n\n"
        "## Recovery\nRotate the redis-credentials secret and restart the deployment.\n"
    )
    response = await client.post(
        "/api/v1/connectors",
        json={
            "name": "local-docs",
            "type": "local_files",
            "config": {"path": str(tmp_path / "docs")},
        },
    )
    assert response.status_code == 201, response.text
    connector_id: str = response.json()["id"]
    return connector_id


async def test_connector_lifecycle_and_ingestion(client: AsyncClient, tmp_path: Path) -> None:
    connector_id = await _register_local_connector(client, tmp_path)

    listed = (await client.get("/api/v1/connectors")).json()
    assert [c["name"] for c in listed] == ["local-docs"]

    health = (await client.get(f"/api/v1/connectors/{connector_id}/health")).json()
    assert health["healthy"]

    sync = await client.post(f"/api/v1/connectors/{connector_id}/sync")
    assert sync.status_code == 202
    job_id = sync.json()["job_id"]

    for _ in range(50):  # let the background task run
        await asyncio.sleep(0.05)
        job = (await client.get(f"/api/v1/jobs/{job_id}")).json()
        if job["status"] in ("completed", "failed"):
            break
    assert job["status"] == "completed", job
    assert job["stats"]["created"] == 1
    assert job["stats"]["memories"] >= 1

    documents = (await client.get("/api/v1/documents")).json()
    assert documents[0]["title"] == "Redis Recovery Runbook"

    detail = (await client.get(f"/api/v1/documents/{documents[0]['id']}")).json()
    assert "Rotate the redis-credentials secret" in detail["content"]

    stats = (await client.get("/api/v1/stats")).json()
    assert stats["documents"] == 1 and stats["memories"] >= 1
    assert stats["graph_nodes"] >= 1

    # Re-syncing is idempotent: connector checkpoint skips unchanged files.
    resync = await client.post(f"/api/v1/connectors/{connector_id}/sync")
    job2_id = resync.json()["job_id"]
    for _ in range(50):
        await asyncio.sleep(0.05)
        job2 = (await client.get(f"/api/v1/jobs/{job2_id}")).json()
        if job2["status"] in ("completed", "failed"):
            break
    assert job2["status"] == "completed"
    assert job2["stats"]["documents"] == 0

    assert (await client.get("/api/v1/stats")).json()["documents"] == 1


async def test_connector_validation_errors(client: AsyncClient) -> None:
    bad = await client.post(
        "/api/v1/connectors",
        json={"name": "broken", "type": "local_files", "config": {"path": "/does/not/exist"}},
    )
    assert bad.status_code == 422
    assert bad.json()["error"]["code"] == "CONNECTOR_UNHEALTHY"

    github = await client.post(
        "/api/v1/connectors", json={"name": "gh", "type": "github", "config": {}}
    )
    assert github.status_code == 502
    assert github.json()["error"]["code"] == "CONNECTOR_ERROR"


async def test_search_chat_and_teaching_flow(client: AsyncClient, tmp_path: Path) -> None:
    connector_id = await _register_local_connector(client, tmp_path)
    await client.post(f"/api/v1/connectors/{connector_id}/sync")
    await asyncio.sleep(0.3)

    search = (await client.post("/api/v1/search", json={"query": "redis recovery"})).json()
    assert search["memories"], "expected semantic memories"
    assert any("Redis" in d["title"] for d in search["documents"])

    chat = (await client.post("/api/v1/chat", json={"message": "How do we recover redis?"})).json()
    assert chat["confidence"] > 0
    assert chat["citations"]

    teach = await client.post(
        "/api/v1/experiences",
        json={
            "content": (
                "The redis outage happened because credentials expired. "
                "We fixed it by rotating the secret."
            ),
            "author": "bob",
        },
    )
    assert teach.status_code == 201
    body = teach.json()
    assert body["created"] and body["confidence"] == 0.6

    experiences = (await client.get("/api/v1/experiences")).json()
    assert len(experiences) == 1
    assert experiences[0]["author"] == "bob"

    # Teaching via chat routes to the teaching pipeline.
    taught = (
        await client.post(
            "/api/v1/chat",
            json={"message": "Remember this: kafka lag was fixed by scaling consumers."},
        )
    ).json()
    assert taught["taught"] is True

    graph = (await client.get("/api/v1/graph/redis?depth=2")).json()
    assert isinstance(graph["edges"], list)


async def test_entities_endpoints_empty(client: AsyncClient) -> None:
    for path in ("/api/v1/services", "/api/v1/teams", "/api/v1/incidents", "/api/v1/repositories"):
        response = await client.get(path)
        assert response.status_code == 200
        assert response.json() == []
