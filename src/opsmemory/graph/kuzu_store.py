"""Kuzu-backed GraphStore (ADR-0001).

Kuzu is embedded and synchronous; calls run in a worker thread and are
serialized with a lock because the database is single-writer.
"""

import asyncio
import threading
from pathlib import Path
from typing import Any

import kuzu

from opsmemory.graph.store import GraphEdge, GraphNode

_SCHEMA = (
    "CREATE NODE TABLE IF NOT EXISTS Entity(name STRING, kind STRING, PRIMARY KEY(name))",
    "CREATE REL TABLE IF NOT EXISTS Relates(FROM Entity TO Entity, rel STRING)",
)


class KuzuGraphStore:
    """GraphStore implementation over an embedded Kuzu database."""

    def __init__(self, path: str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = kuzu.Database(path)
        self._conn = kuzu.Connection(self._db)
        self._lock = threading.Lock()
        for statement in _SCHEMA:
            self._execute_sync(statement, {})

    def _execute_sync(self, query: str, params: dict[str, Any]) -> list[list[Any]]:
        """Run one Cypher statement and materialize its rows."""
        with self._lock:
            result = self._conn.execute(query, params)
            assert not isinstance(result, list)  # single-statement queries only
            rows: list[list[Any]] = []
            while result.has_next():
                rows.append(list(result.get_next()))
            return rows

    async def _execute(self, query: str, params: dict[str, Any]) -> list[list[Any]]:
        """Run a statement in a worker thread (Kuzu is synchronous)."""
        return await asyncio.to_thread(self._execute_sync, query, params)

    async def upsert_node(self, node: GraphNode) -> None:
        """MERGE a node by name, updating its kind."""
        await self._execute(
            "MERGE (e:Entity {name: $name}) SET e.kind = $kind",
            {"name": node.name.lower(), "kind": node.kind},
        )

    async def upsert_edge(self, edge: GraphEdge) -> None:
        """MERGE both endpoints and the typed edge between them."""
        await self._execute(
            "MERGE (a:Entity {name: $source}) MERGE (b:Entity {name: $target}) "
            "MERGE (a)-[:Relates {rel: $rel}]->(b)",
            {
                "source": edge.source.lower(),
                "target": edge.target.lower(),
                "rel": edge.relation,
            },
        )

    async def delete_node(self, name: str) -> None:
        """Delete a node and all its edges (used when removing a meeting's traces)."""
        await self._execute(
            "MATCH (e:Entity {name: $name}) DETACH DELETE e", {"name": name.lower()}
        )

    async def neighbors(self, name: str, *, depth: int = 1) -> list[GraphEdge]:
        """Edges within ``depth`` hops of the node, in either direction.

        Implemented as an iterative breadth-first expansion of single-hop
        queries: simple Cypher stays portable across Kuzu versions and the
        traversal budget is already small (PRD retrieval limits).
        """
        return await self._bfs(name, depth=depth, relation=None, directed=False)

    async def dependencies(self, name: str, *, depth: int = 3) -> list[GraphEdge]:
        """Transitive depends_on edges starting from the node."""
        return await self._bfs(name, depth=depth, relation="depends_on", directed=True)

    async def _bfs(
        self, name: str, *, depth: int, relation: str | None, directed: bool
    ) -> list[GraphEdge]:
        """Breadth-first edge expansion from a start node."""
        depth = max(1, min(depth, 5))
        frontier = {name.lower()}
        seen_nodes: set[str] = set(frontier)
        edges: dict[tuple[str, str, str], GraphEdge] = {}
        relation_filter = "AND r.rel = $rel " if relation else ""
        for _ in range(depth):
            if not frontier:
                break
            params: dict[str, Any] = {"names": sorted(frontier)}
            if relation:
                params["rel"] = relation
            rows = await self._execute(
                "MATCH (a:Entity)-[r:Relates]->(b:Entity) "
                "WHERE (list_contains($names, a.name)"
                + ("" if directed else " OR list_contains($names, b.name)")
                + f") {relation_filter}"
                "RETURN a.name, r.rel, b.name",
                params,
            )
            frontier = set()
            for source, rel, target in rows:
                edges[(source, rel, target)] = GraphEdge(source=source, relation=rel, target=target)
                for node in (source, target):
                    if node not in seen_nodes:
                        seen_nodes.add(node)
                        frontier.add(node)
        return list(edges.values())

    async def stats(self) -> dict[str, int]:
        """Node and edge counts."""
        nodes = await self._execute("MATCH (e:Entity) RETURN count(e)", {})
        edges = await self._execute("MATCH ()-[r:Relates]->() RETURN count(r)", {})
        return {
            "graph_nodes": int(nodes[0][0]) if nodes else 0,
            "graph_edges": int(edges[0][0]) if edges else 0,
        }
