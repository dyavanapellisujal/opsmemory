# ADR-0002: Cognee is the central memory engine, behind a MemoryEngine port

Date: 2026-07-03 · Updated: 2026-07-04 · Status: Accepted

## Context

The PRD designates the open-source **Cognee** (github.com/topoteretes/cognee)
as the organizational memory engine — every piece of knowledge should be
cognified into a connected knowledge graph, not just stored as isolated
vectors. Cognee is a heavy (~130-package) tree, its API moves quickly, and it
requires LLM + embedding credentials to build the graph. We still want a port
so the platform can degrade gracefully and swap adapters, but Cognee must be
the engine in the path for every write, not an opt-in.

## Decision

Define a **`MemoryEngine` port** (add / search / delete). Cognee is the
**central, compulsory, default** engine:

1. **CogneeMemoryEngine** (`memory_engine=cognee`, the default; `cognee` is a
   **core dependency**, not an extra). It composes the native pgvector store
   as the durable, traceable substrate (source of truth, ADR-0003) that backs
   the citations the API returns, and **cognifies every write** into Cognee's
   knowledge graph. Cognification runs in the background (writes never block on
   LLM calls) and is serialized (Cognee's pipeline is not concurrency-safe).
2. **NativeMemoryEngine** (`memory_engine=native`) — the raw pgvector
   substrate, used by the test suite so it stays keyless and offline.

Cognification needs an LLM + embeddings (Gemini). When those are absent
(keyless dev / tests), the engine transparently uses the substrate and logs
that cognification is inactive — Cognee is still the engine in the path, it
just cannot build the graph with no model to call. This is an inherent Cognee
requirement, not optionality.

## Consequences

- Cognee sits behind everything stored, satisfying the PRD's "store
  understanding, not documents" intent, while pgvector keeps retrieval
  traceable and incident-scoped.
- A Cognee breaking change is absorbed in one adapter module; a catastrophic
  construction failure falls back to the substrate loudly (factory-level).
- Tests remain keyless: they select `native` and an autouse fixture strips
  `OPSMEMORY_*` (Cognee's `load_dotenv()` on import would otherwise leak the
  project `.env` into `os.environ`).
- The container image and `uv sync` carry Cognee's full dependency tree.
