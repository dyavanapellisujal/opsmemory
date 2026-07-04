"""MemoryEngine port (ADR-0002): stores and retrieves semantic memories."""

import uuid
from typing import Any, Protocol

from pydantic import BaseModel, Field

from opsmemory.domain.enums import MemoryKind


class MemoryItem(BaseModel):
    """A unit of knowledge to store as a semantic memory."""

    kind: MemoryKind
    content: str
    section: str | None = None
    confidence: float = 0.5
    document_id: uuid.UUID | None = None
    experience_id: uuid.UUID | None = None
    incident_id: uuid.UUID | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class ScoredMemory(BaseModel):
    """A retrieved memory with its similarity score and provenance."""

    id: uuid.UUID
    kind: MemoryKind
    content: str
    section: str | None = None
    score: float = Field(description="Cosine similarity in [0, 1].")
    confidence: float
    document_id: uuid.UUID | None = None
    experience_id: uuid.UUID | None = None
    incident_id: uuid.UUID | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class MemoryEngine(Protocol):
    """Port for semantic memory storage and retrieval.

    Implementations: :class:`~opsmemory.memory.native.NativeMemoryEngine`
    (pgvector, default) and the optional Cognee adapter.
    """

    name: str

    async def add(self, items: list[MemoryItem]) -> list[uuid.UUID]:
        """Embed and persist memories, returning their ids (idempotent by content hash)."""
        ...

    async def search(
        self, query: str, *, limit: int = 5, kinds: list[MemoryKind] | None = None
    ) -> list[ScoredMemory]:
        """Retrieve the most semantically similar memories for a query."""
        ...

    async def delete_for_document(self, document_id: uuid.UUID) -> int:
        """Remove memories derived from a document (used on re-ingestion)."""
        ...

    async def delete_for_meeting(self, meeting_id: uuid.UUID) -> int:
        """Remove memories derived from a meeting (used on meeting deletion)."""
        ...

    async def delete_for_experience(self, experience_id: uuid.UUID) -> int:
        """Remove memories derived from an operational experience."""
        ...
