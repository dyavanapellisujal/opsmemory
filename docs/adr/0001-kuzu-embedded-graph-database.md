# ADR-0001: Kuzu as the graph database, behind a GraphStore port

Date: 2026-07-03 · Status: Accepted

## Context

The PRD requires a graph database for engineering relationships and lists
Neo4j, Kuzu, and Memgraph as candidates. Kuzu is embedded (in-process,
file-backed): zero operational overhead and ideal for the MVP and the local
lab — but it is **single-writer** and cannot be shared by multiple stateless
API replicas, which conflicts with the deployment goal of 2+ API replicas.

## Decision

Use **Kuzu** for the MVP, accessed exclusively through a `GraphStore` port
(interface) owned by the graph layer:

- All graph **writes** happen in the background worker (single writer).
- The API reads graph data through the port; in multi-replica deployments
  the port implementation can proxy to the worker or use a read-only copy.
- The port's contract is small (upsert nodes/edges, traverse, neighbors) so
  a **Neo4j adapter** can replace Kuzu for enterprise deployments without
  touching retrieval logic.

## Consequences

- MVP needs no extra database service; `make lab` stays lightweight.
- Graph writes are serialized through the worker — acceptable because graph
  updates are ingestion-driven, not request-driven.
- The graph is derived data (see ADR-0003) and can be rebuilt from
  PostgreSQL at any time, which also makes switching adapters cheap.
