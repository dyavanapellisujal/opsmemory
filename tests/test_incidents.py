"""Incident-hub API and service tests (auth disabled in the test settings)."""

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from opsmemory.graph.kuzu_store import KuzuGraphStore
from opsmemory.incidents.service import IncidentService
from opsmemory.memory.native import NativeMemoryEngine
from opsmemory.teaching.service import TeachingService


async def _create(client: AsyncClient, title: str, description: str = "") -> dict:
    response = await client.post(
        "/api/v1/incidents", json={"title": title, "description": description, "severity": "sev2"}
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_incident_crud_and_reference(client: AsyncClient) -> None:
    created = await _create(client, "Redis outage", "payments-api down")
    assert created["reference"].startswith("INC-")
    assert created["counts"]["documents"] == 0

    listed = (await client.get("/api/v1/incidents")).json()
    assert len(listed) == 1

    updated = await client.patch(f"/api/v1/incidents/{created['id']}", json={"status": "resolved"})
    assert updated.json()["status"] == "resolved"

    archived = await client.post(f"/api/v1/incidents/{created['id']}/archive")
    assert archived.json()["archived"] is True
    assert (await client.get("/api/v1/incidents")).json() == []
    assert len((await client.get("/api/v1/incidents?include_archived=true")).json()) == 1


async def test_document_upload_enriches_and_generates_documentation(
    client: AsyncClient,
) -> None:
    incident = await _create(client, "Redis auth outage")
    upload = await client.post(
        f"/api/v1/incidents/{incident['id']}/documents",
        json={
            "title": "Redis Recovery Runbook",
            "content": (
                "# Redis Recovery\n\n"
                "payments-api depends on redis.\n\n"
                "## Recovery\nRotate the redis-credentials secret and restart the deployment."
            ),
            "content_type": "markdown",
        },
    )
    assert upload.status_code == 201, upload.text
    assert upload.json()["memories_added"] >= 1

    detail = (await client.get(f"/api/v1/incidents/{incident['id']}")).json()
    assert detail["counts"]["documents"] == 1
    assert detail["counts"]["memories"] >= 1
    section_keys = {s["key"] for s in detail["documentation"]["sections"]}
    assert "references" in section_keys and "evidence" in section_keys
    assert any(d["label"] == "Redis Recovery Runbook" for d in detail["documents"])


async def test_manual_knowledge_updates_incident_and_docs(client: AsyncClient) -> None:
    incident = await _create(client, "Kafka lag incident")
    entry = await client.post(
        f"/api/v1/incidents/{incident['id']}/knowledge",
        json={"kind": "root_cause", "content": "Consumer group rebalance storm under load"},
    )
    assert entry.status_code == 201

    detail = (await client.get(f"/api/v1/incidents/{incident['id']}")).json()
    assert "rebalance" in (detail["root_cause"] or "")
    keys = {s["key"]: s for s in detail["documentation"]["sections"]}
    assert "root_cause" in keys


async def test_incident_scoped_chat_uses_only_incident_knowledge(client: AsyncClient) -> None:
    incident = await _create(client, "Redis recovery")
    await client.post(
        f"/api/v1/incidents/{incident['id']}/documents",
        json={
            "title": "Runbook",
            "content": "Rotate the redis-credentials secret and restart the deployment.",
            "content_type": "text",
        },
    )
    answer = await client.post(
        f"/api/v1/incidents/{incident['id']}/chat",
        json={"message": "How do we recover redis?"},
    )
    body = answer.json()
    assert body["confidence"] >= 0.0
    assert "rotate" in body["answer"].lower() or "redis" in body["answer"].lower()

    # A brand-new incident with no knowledge is honest about it.
    empty = await _create(client, "Empty incident")
    empty_answer = (
        await client.post(
            f"/api/v1/incidents/{empty['id']}/chat", json={"message": "what happened?"}
        )
    ).json()
    assert empty_answer["confidence"] == 0.0


async def test_suggestions_and_linking(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    memory_engine: NativeMemoryEngine,
    graph_store: KuzuGraphStore,
) -> None:
    first = await _create(client, "Redis outage A", "redis authentication failure")
    second = await _create(client, "Redis outage B", "redis authentication failure")
    for incident_id, text in (
        (
            first["id"],
            "Redis authentication failed because credentials expired; rotate the secret.",
        ),
        (
            second["id"],
            "Redis auth failure from expired credentials; we rotated the kubernetes secret.",
        ),
    ):
        await client.post(
            f"/api/v1/incidents/{incident_id}/documents",
            json={"title": "notes", "content": text, "content_type": "text"},
        )

    # Service-level check with a low threshold keeps the assertion deterministic.
    service = IncidentService(
        session_factory,
        memory_engine,
        graph_store,
        TeachingService(session_factory, memory_engine, graph_store, llm=None),
    )
    import uuid

    suggestions = await service.suggest_related(uuid.UUID(second["id"]), min_similarity=0.1)
    assert any(s.reference == first["reference"] for s in suggestions)

    link = await client.post(
        f"/api/v1/incidents/{second['id']}/links",
        json={"target_id": first["id"], "reason": "same root cause", "similarity": 0.9},
    )
    assert link.status_code == 201
    detail = (await client.get(f"/api/v1/incidents/{second['id']}")).json()
    assert any(link_["target_id"] == first["id"] for link_ in detail["links"])


async def test_dashboard_summarizes_memory(client: AsyncClient) -> None:
    await _create(client, "Incident one")
    await _create(client, "Incident two")
    dashboard = (await client.get("/api/v1/dashboard")).json()
    assert dashboard["total_incidents"] == 2
    assert dashboard["active_incidents"] >= 1
    assert len(dashboard["recent_incidents"]) == 2


async def test_global_assistant_returns_related_incidents(client: AsyncClient) -> None:
    incident = await _create(client, "Redis outage")
    await client.post(
        f"/api/v1/incidents/{incident['id']}/documents",
        json={
            "title": "notes",
            "content": "Redis authentication failure; rotate the secret.",
            "content_type": "text",
        },
    )
    response = (
        await client.post("/api/v1/assistant", json={"message": "redis authentication failure"})
    ).json()
    assert "answer" in response
    assert any(r["reference"] == incident["reference"] for r in response["related_incidents"])
