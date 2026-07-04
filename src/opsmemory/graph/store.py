"""GraphStore port: relationship storage for the knowledge graph."""

from typing import Protocol

from pydantic import BaseModel


class GraphNode(BaseModel):
    """A node in the knowledge graph."""

    name: str
    kind: str  # service | document | team | incident | experience | technology


class GraphEdge(BaseModel):
    """A directed relationship between two nodes."""

    source: str
    relation: str
    target: str


class GraphStore(Protocol):
    """Port for knowledge-graph storage and traversal (ADR-0001).

    The graph is a derived projection (ADR-0003) — implementations may be
    dropped and rebuilt from PostgreSQL at any time.
    """

    async def upsert_node(self, node: GraphNode) -> None:
        """Create or update a node (idempotent)."""
        ...

    async def upsert_edge(self, edge: GraphEdge) -> None:
        """Create or update a directed edge (idempotent, creates endpoints)."""
        ...

    async def delete_node(self, name: str) -> None:
        """Delete a node and all edges touching it (idempotent)."""
        ...

    async def neighbors(self, name: str, *, depth: int = 1) -> list[GraphEdge]:
        """Edges reachable from a node within ``depth`` hops (either direction)."""
        ...

    async def dependencies(self, name: str, *, depth: int = 3) -> list[GraphEdge]:
        """Transitive ``depends_on`` edges from a node."""
        ...

    async def stats(self) -> dict[str, int]:
        """Node and edge counts."""
        ...
