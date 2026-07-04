"""Native memory engine: pgvector-backed semantic memory (ADR-0002 fallback/default).

On PostgreSQL, similarity search uses the pgvector ``<=>`` cosine-distance
operator; on other dialects (SQLite in tests) it falls back to in-Python
cosine over the JSON-stored vectors.
"""

import hashlib
import math
import uuid
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import Float, cast, literal, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from opsmemory.ai.base import EmbeddingProvider
from opsmemory.db.models import Memory
from opsmemory.domain.enums import MemoryKind
from opsmemory.memory.base import MemoryItem, ScoredMemory


class NativeMemoryEngine:
    """MemoryEngine backed by the ``memories`` table and pgvector."""

    name = "native"

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        embeddings: EmbeddingProvider,
    ) -> None:
        self._session_factory = session_factory
        self._embeddings = embeddings

    async def add(self, items: list[MemoryItem]) -> list[uuid.UUID]:
        """Embed and persist memories; unchanged content re-uses embeddings but gets new rows."""
        if not items:
            return []
        async with self._session_factory() as session:
            new_items: list[tuple[MemoryItem, str]] = []
            cached_embeddings: dict[str, Any] = {}
            ids: list[uuid.UUID] = []
            for item in items:
                digest = hashlib.sha256(item.content.encode()).hexdigest()
                new_items.append((item, digest))
                if digest not in cached_embeddings:
                    existing = (
                        await session.execute(
                            select(Memory.embedding)
                            .where(Memory.content_hash == digest, Memory.kind == item.kind)
                            .limit(1)
                        )
                    ).scalar_one_or_none()
                    if existing is not None:
                        cached_embeddings[digest] = existing

            items_to_embed = [
                (item, digest) for item, digest in new_items if digest not in cached_embeddings
            ]
            if items_to_embed:
                vectors = await self._embeddings.embed([i.content for i, _ in items_to_embed])
                for (_item, digest), vector in zip(items_to_embed, vectors, strict=True):
                    cached_embeddings[digest] = vector

            for item, digest in new_items:
                vector = cached_embeddings[digest]
                memory = Memory(
                    kind=item.kind,
                    content=item.content,
                    section=item.section,
                    embedding=vector,
                    embedding_model=self._embeddings.name,
                    confidence=item.confidence,
                    content_hash=digest,
                    meta=item.meta,
                    document_id=item.document_id,
                    experience_id=item.experience_id,
                    incident_id=item.incident_id,
                )
                session.add(memory)
                await session.flush()
                ids.append(memory.id)
            await session.commit()
            return ids

    async def search(
        self, query: str, *, limit: int = 5, kinds: list[MemoryKind] | None = None
    ) -> list[ScoredMemory]:
        """Retrieve the most similar memories via pgvector or Python fallback."""
        [vector] = await self._embeddings.embed([query])
        async with self._session_factory() as session:
            if session.bind is not None and session.bind.dialect.name == "postgresql":
                return await self._search_pgvector(session, vector, limit, kinds)
            return await self._search_python(session, vector, limit, kinds)

    async def delete_for_document(self, document_id: uuid.UUID) -> int:
        """Delete all memories derived from the given document."""
        async with self._session_factory() as session:
            rows = (
                (await session.execute(select(Memory).where(Memory.document_id == document_id)))
                .scalars()
                .all()
            )
            for row in rows:
                await session.delete(row)
            await session.commit()
            return len(rows)

    async def delete_for_experience(self, experience_id: uuid.UUID) -> int:
        """Delete memories derived from an operational experience."""
        async with self._session_factory() as session:
            rows = (
                (await session.execute(select(Memory).where(Memory.experience_id == experience_id)))
                .scalars()
                .all()
            )
            for row in rows:
                await session.delete(row)
            await session.commit()
            return len(rows)

    async def delete_for_meeting(self, meeting_id: uuid.UUID) -> int:
        """Delete memories derived from a meeting (matched via ``meta.meeting_id``)."""
        target = str(meeting_id)
        async with self._session_factory() as session:
            rows = (
                (await session.execute(select(Memory).where(Memory.kind == MemoryKind.SUMMARY)))
                .scalars()
                .all()
            )
            removed = 0
            for row in rows:
                if (row.meta or {}).get("meeting_id") == target:
                    await session.delete(row)
                    removed += 1
            await session.commit()
            return removed

    async def _search_pgvector(
        self,
        session: AsyncSession,
        vector: list[float],
        limit: int,
        kinds: list[MemoryKind] | None,
    ) -> list[ScoredMemory]:
        """ANN search using the pgvector ``<=>`` cosine-distance operator.

        ``Memory.embedding`` is a cross-dialect TypeDecorator, so pgvector's
        comparator methods are not available on the ORM attribute; the
        operator is applied explicitly with a vector-typed literal instead.
        """
        vector_literal = "[" + ",".join(f"{v:.8f}" for v in vector) + "]"
        distance = Memory.embedding.op("<=>", return_type=Float())(
            cast(literal(vector_literal), Vector(len(vector)))
        )
        stmt = select(Memory, distance.label("distance")).where(Memory.embedding.is_not(None))
        if kinds:
            stmt = stmt.where(Memory.kind.in_(kinds))
        stmt = stmt.order_by(distance).limit(limit)
        rows = (await session.execute(stmt)).all()
        return [_scored(memory, 1.0 - float(dist)) for memory, dist in rows]

    async def _search_python(
        self,
        session: AsyncSession,
        vector: list[float],
        limit: int,
        kinds: list[MemoryKind] | None,
    ) -> list[ScoredMemory]:
        """Exact cosine search in Python (non-PostgreSQL dialects, i.e. tests)."""
        stmt = select(Memory).where(Memory.embedding.is_not(None))
        if kinds:
            stmt = stmt.where(Memory.kind.in_(kinds))
        memories = (await session.execute(stmt)).scalars().all()
        scored = [(m, _cosine(vector, m.embedding or [])) for m in memories]
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return [_scored(m, s) for m, s in scored[:limit]]


def _cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity of two vectors (0.0 when shapes mismatch)."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


def _scored(memory: Memory, score: float) -> ScoredMemory:
    """Convert an ORM memory + score into the port's return model."""
    meta: dict[str, Any] = memory.meta or {}
    return ScoredMemory(
        id=memory.id,
        kind=memory.kind,
        content=memory.content,
        section=memory.section,
        score=max(0.0, min(1.0, score)),
        confidence=memory.confidence,
        document_id=memory.document_id,
        experience_id=memory.experience_id,
        incident_id=memory.incident_id,
        meta=meta,
    )
