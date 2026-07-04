"""Cognee memory engine — the central organizational-memory engine (ADR-0002).

Cognee sits behind *every* write: each memory item is cognified into
Cognee's knowledge graph so the organization's memory is a connected graph,
not just isolated vectors. The platform's own PostgreSQL + pgvector remains
the durable, traceable substrate (source of truth, ADR-0003) that backs the
citations the API returns; this engine composes it and layers Cognee on top.

Cognification needs an LLM + embeddings. When those are configured, every
write is graph-cognified (in the background so requests never block on LLM
calls). When they are absent (keyless dev / tests), the engine transparently
uses the substrate and logs that cognification is inactive — Cognee is still
the engine in the path, it just cannot build the graph with no model to call.
"""

import asyncio
import uuid
from pathlib import Path
from typing import Any

from opsmemory.core.config import Settings
from opsmemory.core.logging import get_logger
from opsmemory.domain.enums import MemoryKind
from opsmemory.memory.base import MemoryItem, ScoredMemory
from opsmemory.memory.native import NativeMemoryEngine

logger = get_logger(__name__)


class CogneeMemoryEngine:
    """Central memory engine: cognifies every write, substrate-backed retrieval."""

    name = "cognee"

    def __init__(self, native: NativeMemoryEngine, settings: Settings) -> None:
        self._native = native
        self._settings = settings
        self._lock = asyncio.Lock()
        self._tasks: set[asyncio.Task[None]] = set()
        self._cognee: Any = None
        self._search_type: Any = None
        self._cognify_enabled = False
        self._configure(settings)

    def _configure(self, settings: Settings) -> None:
        """Import and configure Cognee against the platform's providers/storage.

        Best-effort and fail-safe: any configuration problem disables
        cognification (the substrate keeps the platform fully functional)
        rather than breaking startup.
        """
        try:
            import cognee
            from cognee.modules.search.types import SearchType
        except Exception as exc:  # pragma: no cover - cognee is a core dependency
            logger.warning("Cognee unavailable (%s); using the pgvector substrate only", exc)
            return
        self._cognee = cognee
        self._search_type = SearchType

        # Embeddings drive cognification; Gemini is required (Groq has none).
        if not (settings.cognee_cognify and settings.gemini_api_key):
            logger.warning(
                "Cognee cognification inactive (no Gemini embedding key); "
                "storing via the pgvector substrate. Set OPSMEMORY_GEMINI_API_KEY to "
                "build the knowledge graph."
            )
            return

        try:
            storage = Path(settings.graph_db_path).parent / "cognee"
            storage.mkdir(parents=True, exist_ok=True)
            cognee.config.system_root_directory(str(storage / "system"))
            cognee.config.data_root_directory(str(storage / "data"))

            cognee.config.set_embedding_provider("gemini")
            cognee.config.set_embedding_api_key(settings.gemini_api_key)
            cognee.config.set_embedding_model(f"gemini/{settings.gemini_embedding_model}")
            cognee.config.set_embedding_dimensions(settings.embedding_dimension)

            # Reasoning: prefer Gemini (key present); else Groq via litellm.
            if settings.gemini_api_key:
                cognee.config.set_llm_provider("gemini")
                cognee.config.set_llm_api_key(settings.gemini_api_key)
                cognee.config.set_llm_model(f"gemini/{settings.gemini_model}")
            elif settings.groq_api_key:
                cognee.config.set_llm_provider("groq")
                cognee.config.set_llm_api_key(settings.groq_api_key)
                cognee.config.set_llm_model(f"groq/{settings.groq_model}")
            self._cognify_enabled = True
            logger.info("Cognee configured as the central memory engine (storage=%s)", storage)
        except Exception as exc:
            logger.warning("Cognee configuration failed (%s); using the substrate only", exc)
            self._cognify_enabled = False

    async def add(self, items: list[MemoryItem]) -> list[uuid.UUID]:
        """Persist to the substrate (source of truth) and cognify in the background."""
        ids = await self._native.add(items)
        if self._cognify_enabled and items:
            self._schedule_cognify([i.content for i in items])
        return ids

    def _schedule_cognify(self, contents: list[str]) -> None:
        """Run Cognee add+cognify off the request path (never blocks the caller)."""
        task = asyncio.create_task(self._cognify(contents))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _cognify(self, contents: list[str]) -> None:
        """Feed content into Cognee and rebuild the knowledge graph (serialized)."""
        async with self._lock:  # Cognee's pipeline is not concurrency-safe
            try:
                for content in contents:
                    await self._cognee.add(content)
                await self._cognee.cognify()
                logger.info("Cognee cognified %d item(s) into the knowledge graph", len(contents))
            except Exception as exc:
                logger.warning("Cognee cognify failed (%s); substrate retains the data", exc)

    async def search(
        self, query: str, *, limit: int = 5, kinds: list[MemoryKind] | None = None
    ) -> list[ScoredMemory]:
        """Retrieve traceable memories from the substrate (backs API citations)."""
        return await self._native.search(query, limit=limit, kinds=kinds)

    async def recall(self, query: str) -> str | None:
        """Graph-aware answer from Cognee's knowledge graph, when available."""
        if not self._cognify_enabled:
            return None
        try:  # pragma: no cover - requires LLM credentials + network
            results = await self._cognee.search(
                query_text=query, query_type=self._search_type.GRAPH_COMPLETION, top_k=5
            )
            if not results:
                return None
            first = results[0]
            return str(getattr(first, "value", None) or getattr(first, "text", None) or first)
        except Exception as exc:
            logger.warning("Cognee recall failed (%s)", exc)
            return None

    async def delete_for_meeting(self, meeting_id: uuid.UUID) -> int:
        """Delete meeting-derived memories from the substrate."""
        return await self._native.delete_for_meeting(meeting_id)

    async def delete_for_experience(self, experience_id: uuid.UUID) -> int:
        """Delete experience-derived memories from the substrate."""
        return await self._native.delete_for_experience(experience_id)

    async def delete_for_document(self, document_id: uuid.UUID) -> int:
        """Delete document-derived memories from the substrate."""
        return await self._native.delete_for_document(document_id)
