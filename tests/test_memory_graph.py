"""Tests for the native memory engine and the Kuzu graph store."""

import uuid

from opsmemory.domain.enums import MemoryKind
from opsmemory.graph.kuzu_store import KuzuGraphStore
from opsmemory.graph.store import GraphEdge, GraphNode
from opsmemory.memory.base import MemoryItem
from opsmemory.memory.native import NativeMemoryEngine


async def test_memory_add_search_and_store(memory_engine: NativeMemoryEngine) -> None:
    items = [
        MemoryItem(kind=MemoryKind.CHUNK, content="Redis authentication failed due to expiry"),
        MemoryItem(kind=MemoryKind.CHUNK, content="Kafka consumer lag runbook and mitigation"),
        MemoryItem(kind=MemoryKind.EXPERIENCE, content="Rotate redis secret to fix auth failure"),
    ]
    ids = await memory_engine.add(items)
    assert len(ids) == 3

    # Each add creates fresh rows (identical content across incidents must not
    # collapse); the embedding is reused so no extra provider calls are made.
    again = await memory_engine.add(items)
    assert len(again) == 3
    assert set(again).isdisjoint(ids)

    results = await memory_engine.search("redis authentication failure", limit=2)
    assert results and "edis" in results[0].content
    assert results[0].score >= results[-1].score

    only_exp = await memory_engine.search("redis", limit=5, kinds=[MemoryKind.EXPERIENCE])
    assert all(m.kind is MemoryKind.EXPERIENCE for m in only_exp)


async def test_memory_delete_for_document(memory_engine: NativeMemoryEngine) -> None:
    doc_id = uuid.uuid4()
    await memory_engine.add(
        [
            MemoryItem(kind=MemoryKind.CHUNK, content="doc chunk one", document_id=doc_id),
            MemoryItem(kind=MemoryKind.CHUNK, content="doc chunk two", document_id=doc_id),
            MemoryItem(kind=MemoryKind.CHUNK, content="other doc chunk"),
        ]
    )
    assert await memory_engine.delete_for_document(doc_id) == 2
    remaining = await memory_engine.search("doc chunk", limit=10)
    assert len(remaining) == 1


async def test_graph_upsert_neighbors_dependencies(graph_store: KuzuGraphStore) -> None:
    await graph_store.upsert_node(GraphNode(name="payments-api", kind="service"))
    await graph_store.upsert_edge(
        GraphEdge(source="payments-api", relation="depends_on", target="redis")
    )
    await graph_store.upsert_edge(
        GraphEdge(source="redis", relation="depends_on", target="ebs-volume")
    )
    await graph_store.upsert_edge(
        GraphEdge(source="payments-api", relation="owned_by", target="platform-team")
    )
    # Idempotent upserts must not duplicate edges.
    await graph_store.upsert_edge(
        GraphEdge(source="payments-api", relation="depends_on", target="redis")
    )

    neighbors = await graph_store.neighbors("payments-api", depth=1)
    relations = {(e.source, e.relation, e.target) for e in neighbors}
    assert ("payments-api", "depends_on", "redis") in relations
    assert ("payments-api", "owned_by", "platform-team") in relations

    deps = await graph_store.dependencies("payments-api", depth=3)
    targets = {e.target for e in deps}
    assert targets == {"redis", "ebs-volume"}

    stats = await graph_store.stats()
    assert stats["graph_nodes"] == 4
    assert stats["graph_edges"] == 3
