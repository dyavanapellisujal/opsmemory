# ADR-0003: PostgreSQL is the single source of truth; graph and vectors are derived

Date: 2026-07-03 · Status: Accepted

## Context

OpsMemory uses polyglot persistence (PostgreSQL, pgvector, graph database,
Cognee). The PRD requires "consistency across storage layers" but does not
specify how consistency is achieved. Distributed transactions across these
stores are not practical.

## Decision

- **PostgreSQL holds the authoritative copy** of every entity, document,
  relationship record, and operational experience.
- **pgvector embeddings, the knowledge graph, and Cognee memories are
  derived, rebuildable projections.** Any of them can be dropped and rebuilt
  from PostgreSQL (`opsmemory memories rebuild`).
- Ingestion writes to PostgreSQL first (transactionally), then projects to
  the derived stores; a failed projection is retried by the worker and never
  leaves PostgreSQL inconsistent.

## Consequences

- No cross-store transactions needed; recovery is "rebuild the projection".
- Backup/DR story reduces to PostgreSQL backups plus re-projection.
- Derived stores may briefly lag the source of truth — acceptable for a
  knowledge platform (eventual consistency, seconds-scale).
