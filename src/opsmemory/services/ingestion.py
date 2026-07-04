"""Ingestion service: runs the full pipeline for a configured connector.

connector → parse → upsert document → chunk → embed (memories) →
relationships → graph projection → (experience extraction for incident docs).

Idempotent: documents are matched by source identifier and skipped when
their content hash is unchanged; connector checkpoints skip unchanged
resources at the source.
"""

import hashlib
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from opsmemory.connectors.registry import build_connector
from opsmemory.core.errors import NotFoundError
from opsmemory.core.logging import get_logger
from opsmemory.db.models import Connector, Document, Service
from opsmemory.domain.enums import ConnectorStatus, ExperienceSource, MemoryKind
from opsmemory.graph.store import GraphEdge, GraphNode, GraphStore
from opsmemory.memory.base import MemoryEngine, MemoryItem
from opsmemory.processing.chunker import chunk_document
from opsmemory.processing.models import NormalizedDocument
from opsmemory.processing.parsers import parse
from opsmemory.processing.relationships import extract_relationships
from opsmemory.teaching.service import TeachingService

logger = get_logger(__name__)

_EXPERIENCE_TAGS = {"incident", "postmortem"}


class IngestionService:
    """Executes the knowledge processing pipeline for one connector."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        memory_engine: MemoryEngine,
        graph: GraphStore,
        teaching: TeachingService | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._memory = memory_engine
        self._graph = graph
        self._teaching = teaching

    async def ingest(self, connector_id: uuid.UUID) -> dict[str, Any]:
        """Synchronize one connector end to end.

        Returns:
            Statistics: documents seen/created/updated/skipped, memories, edges.

        Raises:
            NotFoundError: If the connector does not exist.
        """
        async with self._session_factory() as session:
            connector_row = (
                await session.execute(select(Connector).where(Connector.id == connector_id))
            ).scalar_one_or_none()
            if connector_row is None:
                raise NotFoundError(f"Connector {connector_id} not found")
            connector = build_connector(
                connector_row.type, connector_row.config, connector_row.checkpoint
            )
            known_services = list((await session.execute(select(Service.name))).scalars().all())

        stats: dict[str, Any] = {
            "documents": 0,
            "created": 0,
            "updated": 0,
            "unchanged": 0,
            "memories": 0,
            "edges": 0,
        }
        try:
            async for raw in connector.discover():
                normalized = parse(raw, connector.source)
                stats["documents"] += 1
                outcome, document_id = await self._upsert_document(normalized, connector_id)
                stats[outcome] += 1
                if outcome == "unchanged" or document_id is None:
                    continue
                stats["memories"] += await self._build_memories(normalized, document_id)
                stats["edges"] += await self._project_graph(normalized, known_services)
                await self._maybe_extract_experience(normalized)
            status, error = ConnectorStatus.ACTIVE, None
        except Exception as exc:
            logger.exception("Ingestion failed for connector %s", connector_id)
            status, error = ConnectorStatus.ERROR, str(exc)

        async with self._session_factory() as session:
            row = (
                await session.execute(select(Connector).where(Connector.id == connector_id))
            ).scalar_one()
            row.checkpoint = connector.checkpoint
            row.last_sync_at = datetime.now(UTC).replace(tzinfo=None)
            row.status = status
            await session.commit()
        if error is not None:
            stats["error"] = error
        return stats

    async def _upsert_document(
        self, normalized: NormalizedDocument, connector_id: uuid.UUID
    ) -> tuple[str, uuid.UUID | None]:
        """Create or update the document row; returns (outcome, id)."""
        digest = hashlib.sha256(normalized.content.encode()).hexdigest()
        async with self._session_factory() as session:
            existing = (
                await session.execute(
                    select(Document).where(
                        Document.connector_id == connector_id,
                        Document.extra["identifier"].as_string() == normalized.identifier
                        if session.bind is not None and session.bind.dialect.name == "postgresql"
                        else Document.url == normalized.url,
                    )
                )
            ).scalar_one_or_none()

            if existing is not None and existing.content_hash == digest:
                return "unchanged", existing.id

            if existing is not None:
                existing.title = normalized.title
                existing.content = normalized.content
                existing.content_hash = digest
                existing.tags = normalized.tags
                existing.last_modified = _naive(normalized.last_modified)
                existing.extra = {**normalized.metadata, "identifier": normalized.identifier}
                await session.commit()
                await self._memory.delete_for_document(existing.id)
                return "updated", existing.id

            document = Document(
                title=normalized.title,
                source=normalized.source,
                url=normalized.url,
                content=normalized.content,
                content_hash=digest,
                tags=normalized.tags,
                extra={**normalized.metadata, "identifier": normalized.identifier},
                last_modified=_naive(normalized.last_modified),
                connector_id=connector_id,
            )
            session.add(document)
            await session.commit()
            return "created", document.id

    async def _build_memories(self, normalized: NormalizedDocument, document_id: uuid.UUID) -> int:
        """Chunk the document and store embedded memories."""
        chunks = chunk_document(normalized.content, title=normalized.title)
        items = [
            MemoryItem(
                kind=MemoryKind.CHUNK,
                content=chunk.content,
                section=chunk.section,
                confidence=0.7,  # documented knowledge (PRD confidence model)
                document_id=document_id,
                meta={"document_title": normalized.title, "position": chunk.position},
            )
            for chunk in chunks
        ]
        ids = await self._memory.add(items)
        return len(ids)

    async def _project_graph(
        self, normalized: NormalizedDocument, known_services: list[str]
    ) -> int:
        """Project deterministic relationships into the knowledge graph."""
        await self._graph.upsert_node(GraphNode(name=normalized.title, kind="document"))
        relationships = extract_relationships(normalized, known_services)
        for rel in relationships:
            await self._graph.upsert_edge(
                GraphEdge(source=rel.source_name, relation=rel.relation, target=rel.target_name)
            )
        return len(relationships)

    async def _maybe_extract_experience(self, normalized: NormalizedDocument) -> None:
        """Extract an operational experience from incident/postmortem documents."""
        if self._teaching is None or not (_EXPERIENCE_TAGS & set(normalized.tags)):
            return
        try:
            await self._teaching.teach(
                normalized.content[:6000],
                author=f"document:{normalized.title}",
                source=ExperienceSource.DOCUMENT_EXTRACTION,
            )
        except Exception as exc:
            logger.warning("Experience extraction skipped for %s: %s", normalized.title, exc)


def _naive(value: datetime | None) -> datetime | None:
    """Strip timezone info for storage in naive DateTime columns."""
    return value.replace(tzinfo=None) if value is not None and value.tzinfo else value
