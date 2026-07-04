"""IncidentService: the incident knowledge hub.

Owns incident CRUD, the three data-collection paths (document upload, manual
knowledge entry, meeting attachment), cross-incident AI suggestions, and
living-documentation regeneration. Every ingestion enriches the *same*
incident and links its derived memories/experiences back to it.
"""

import hashlib
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from opsmemory.core.errors import NotFoundError, ValidationFailedError
from opsmemory.core.logging import get_logger
from opsmemory.db.models import (
    Document,
    Incident,
    IncidentEvent,
    IncidentLink,
    Meeting,
    MeetingSummary,
    Memory,
    OperationalExperience,
)
from opsmemory.domain.enums import (
    DocumentSource,
    ExperienceSource,
    IncidentSeverity,
    IncidentStatus,
    MemoryKind,
)
from opsmemory.graph.store import GraphEdge, GraphNode, GraphStore
from opsmemory.incidents.documentation import EvidenceBundle, generate_documentation
from opsmemory.memory.base import MemoryEngine, MemoryItem
from opsmemory.processing.chunker import chunk_document
from opsmemory.processing.models import RawContent
from opsmemory.processing.parsers import parse
from opsmemory.processing.relationships import extract_relationships, extract_technologies
from opsmemory.teaching.service import TeachingService

logger = get_logger(__name__)

_MANUAL_KINDS = {
    "lesson": "Lessons Learned",
    "root_cause": "Root Cause",
    "resolution": "Resolution",
    "architecture_decision": "Architecture Decision",
    "operational_experience": "Operational Experience",
    "action_item": "Action Item",
}


class IncidentSuggestion(BaseModel):
    """An AI-suggested related incident surfaced before/after ingestion."""

    incident_id: uuid.UUID
    reference: str
    title: str
    similarity: float
    shared_services: list[str] = Field(default_factory=list)
    rationale: str


class IngestionOutcome(BaseModel):
    """Result of a data-collection action on an incident."""

    incident_id: uuid.UUID
    memories_added: int = 0
    suggestions: list[IncidentSuggestion] = Field(default_factory=list)


class IncidentService:
    """Business logic for the incident knowledge hub."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        memory_engine: MemoryEngine,
        graph: GraphStore,
        teaching: TeachingService,
    ) -> None:
        self._session_factory = session_factory
        self._memory = memory_engine
        self._graph = graph
        self._teaching = teaching

    # --- CRUD ---------------------------------------------------------------

    async def create(
        self,
        title: str,
        *,
        description: str | None = None,
        severity: IncidentSeverity = IncidentSeverity.SEV3,
        status: IncidentStatus = IncidentStatus.OPEN,
    ) -> Incident:
        """Create a new incident hub with the next sequential number."""
        async with self._session_factory() as session:
            next_number = (
                await session.execute(select(func.coalesce(func.max(Incident.number), 1000)))
            ).scalar_one()
            incident = Incident(
                number=int(next_number or 1000) + 1,
                title=title,
                description=description,
                severity=severity,
                status=status,
            )
            session.add(incident)
            await session.commit()
            incident_id = incident.id
        await self._graph.upsert_node(GraphNode(name=f"incident:{title}", kind="incident"))
        await self.regenerate_documentation(incident_id)
        logger.info("Incident created incident_id=%s number=%s", incident_id, incident.number)
        return await self.get(incident_id)

    async def get(self, incident_id: uuid.UUID) -> Incident:
        """Fetch an incident or raise 404."""
        async with self._session_factory() as session:
            incident = (
                await session.execute(select(Incident).where(Incident.id == incident_id))
            ).scalar_one_or_none()
            if incident is None:
                raise NotFoundError(f"Incident {incident_id} not found", code="INCIDENT_NOT_FOUND")
            return incident

    async def list_incidents(self, *, include_archived: bool = False) -> list[Incident]:
        """List incidents, newest first."""
        async with self._session_factory() as session:
            stmt = select(Incident).order_by(Incident.updated_at.desc())
            if not include_archived:
                stmt = stmt.where(Incident.archived.is_(False))
            return list((await session.execute(stmt)).scalars().all())

    async def update(self, incident_id: uuid.UUID, **fields: Any) -> Incident:
        """Update incident metadata and regenerate documentation."""
        allowed = {
            "title",
            "description",
            "severity",
            "status",
            "root_cause",
            "resolution",
            "lessons_learned",
        }
        async with self._session_factory() as session:
            incident = (
                await session.execute(select(Incident).where(Incident.id == incident_id))
            ).scalar_one_or_none()
            if incident is None:
                raise NotFoundError(f"Incident {incident_id} not found", code="INCIDENT_NOT_FOUND")
            for key, value in fields.items():
                if value is not None and key in allowed:
                    setattr(incident, key, value)
            await session.commit()
        await self.regenerate_documentation(incident_id)
        return await self.get(incident_id)

    async def archive(self, incident_id: uuid.UUID, *, archived: bool = True) -> Incident:
        """Archive (or restore) an incident."""
        async with self._session_factory() as session:
            incident = (
                await session.execute(select(Incident).where(Incident.id == incident_id))
            ).scalar_one_or_none()
            if incident is None:
                raise NotFoundError(f"Incident {incident_id} not found", code="INCIDENT_NOT_FOUND")
            incident.archived = archived
            await session.commit()
        return await self.get(incident_id)

    async def counts(self, incident_id: uuid.UUID) -> dict[str, int]:
        """Evidence counts for an incident card."""
        async with self._session_factory() as session:

            async def count(model: Any, column: Any) -> int:
                return (
                    await session.execute(
                        select(func.count()).select_from(model).where(column == incident_id)
                    )
                ).scalar_one()

            return {
                "documents": await count(Document, Document.incident_id),
                "meetings": await count(Meeting, Meeting.incident_id),
                "memories": await count(Memory, Memory.incident_id),
                "experiences": await count(
                    OperationalExperience, OperationalExperience.incident_id
                ),
            }

    # --- Timeline ------------------------------------------------------------

    async def add_event(
        self,
        incident_id: uuid.UUID,
        *,
        kind: str,
        label: str,
        at: datetime | None = None,
        meeting_id: uuid.UUID | None = None,
        meta: dict[str, Any] | None = None,
    ) -> None:
        """Append a timeline event to an incident."""
        async with self._session_factory() as session:
            session.add(
                IncidentEvent(
                    incident_id=incident_id,
                    at=(at or datetime.now(UTC)).replace(tzinfo=None),
                    kind=kind,
                    label=label,
                    meeting_id=meeting_id,
                    meta=meta or {},
                )
            )
            await session.commit()

    async def timeline(self, incident_id: uuid.UUID) -> list[IncidentEvent]:
        """Return an incident's timeline events, oldest first."""
        async with self._session_factory() as session:
            return list(
                (
                    await session.execute(
                        select(IncidentEvent)
                        .where(IncidentEvent.incident_id == incident_id)
                        .order_by(IncidentEvent.at.asc())
                    )
                )
                .scalars()
                .all()
            )

    # --- Data collection -----------------------------------------------------

    async def add_document(
        self,
        incident_id: uuid.UUID,
        *,
        title: str,
        content: str,
        content_type: str = "markdown",
        author: str | None = None,
    ) -> IngestionOutcome:
        """Ingest an uploaded document into the incident (parse→chunk→memory→graph)."""
        incident = await self.get(incident_id)
        normalized = parse(
            RawContent(
                identifier=f"incident/{incident_id}/{title}",
                content=content,
                content_type=content_type,
                title_hint=title,
            ),
            DocumentSource.USER,
        )
        digest = hashlib.sha256(content.encode()).hexdigest()
        async with self._session_factory() as session:
            document = Document(
                title=normalized.title,
                source=DocumentSource.USER,
                content=normalized.content,
                content_hash=digest,
                tags=normalized.tags,
                author=author,
                extra={"incident": incident.reference},
                incident_id=incident_id,
            )
            session.add(document)
            await session.commit()
            document_id = document.id

        chunks = chunk_document(normalized.content, title=normalized.title)
        items = [
            MemoryItem(
                kind=MemoryKind.CHUNK,
                content=chunk.content,
                section=chunk.section,
                confidence=0.7,
                document_id=document_id,
                incident_id=incident_id,
                meta={"document_title": normalized.title, "incident": incident.reference},
            )
            for chunk in chunks
        ]
        added = await self._memory.add(items)

        # Extract structured operational experience from the document so it
        # appears in the living documentation (Root Cause, Resolution, etc.)
        await self._teaching.teach(
            normalized.content,
            author=author,
            source=ExperienceSource.DOCUMENT_EXTRACTION,
            incident_id=incident_id,
        )

        await self._project_document_graph(incident, normalized.content)
        await self.regenerate_documentation(incident_id)
        logger.info(
            "Incident enriched incident_id=%s source=document memories=%d",
            incident_id,
            len(added),
        )
        suggestions = await self.suggest_related(incident_id)
        return IngestionOutcome(
            incident_id=incident_id, memories_added=len(added), suggestions=suggestions
        )

    async def add_manual_knowledge(
        self,
        incident_id: uuid.UUID,
        *,
        kind: str,
        content: str,
        author: str | None = None,
    ) -> IngestionOutcome:
        """Add a manual knowledge entry (lesson, root cause, resolution, ...)."""
        if kind not in _MANUAL_KINDS:
            raise ValidationFailedError(
                f"Unknown manual knowledge kind {kind!r}; expected one of {sorted(_MANUAL_KINDS)}",
                code="INVALID_KNOWLEDGE_KIND",
            )
        incident = await self.get(incident_id)
        memories_added = 0

        if kind in ("operational_experience", "resolution", "root_cause"):
            # Route through the teaching pipeline so it becomes a first-class
            # operational experience linked to this incident.
            await self._teaching.teach(
                content,
                author=author or "manual",
                source=ExperienceSource.USER_TEACHING,
                incident_id=incident_id,
            )
            memories_added += 1
        else:
            label = _MANUAL_KINDS[kind]
            added = await self._memory.add(
                [
                    MemoryItem(
                        kind=MemoryKind.SUMMARY,
                        content=f"{label}: {content}",
                        section=f"manual:{kind}",
                        confidence=0.7,
                        incident_id=incident_id,
                        meta={"incident": incident.reference, "manual_kind": kind},
                    )
                ]
            )
            memories_added += len(added)

        # Mirror key fields onto the incident record so documentation and the
        # card reflect them immediately.
        field_map = {
            "root_cause": "root_cause",
            "resolution": "resolution",
            "lesson": "lessons_learned",
        }
        if kind in field_map:
            await self._append_incident_field(incident_id, field_map[kind], content)

        for technology in extract_technologies(content):
            await self._graph.upsert_edge(
                GraphEdge(
                    source=f"incident:{incident.title}",
                    relation="references",
                    target=technology,
                )
            )
        await self.regenerate_documentation(incident_id)
        logger.info("Incident enriched incident_id=%s source=manual kind=%s", incident_id, kind)
        suggestions = await self.suggest_related(incident_id)
        return IngestionOutcome(
            incident_id=incident_id, memories_added=memories_added, suggestions=suggestions
        )

    async def attach_meeting(
        self, incident_id: uuid.UUID, meeting_id: uuid.UUID
    ) -> IngestionOutcome:
        """Attach an existing meeting to the incident and adopt its knowledge."""
        await self.get(incident_id)  # 404 if the incident is unknown
        async with self._session_factory() as session:
            meeting = (
                await session.execute(select(Meeting).where(Meeting.id == meeting_id))
            ).scalar_one_or_none()
            if meeting is None:
                raise NotFoundError(f"Meeting {meeting_id} not found", code="MEETING_NOT_FOUND")
            meeting.incident_id = incident_id
            await session.commit()

        # Adopt memories/experiences already extracted from this meeting.
        async with self._session_factory() as session:
            author = "meeting:%"
            experiences = (
                (
                    await session.execute(
                        select(OperationalExperience).where(
                            OperationalExperience.author.like(author),
                            OperationalExperience.incident_id.is_(None),
                        )
                    )
                )
                .scalars()
                .all()
            )
            for experience in experiences:
                experience.incident_id = incident_id
            await session.commit()

        await self.regenerate_documentation(incident_id)
        logger.info("Meeting attached incident_id=%s meeting_id=%s", incident_id, meeting_id)
        suggestions = await self.suggest_related(incident_id)
        return IngestionOutcome(incident_id=incident_id, suggestions=suggestions)

    # --- AI suggestions ------------------------------------------------------

    async def suggest_related(
        self, incident_id: uuid.UUID, *, limit: int = 3, min_similarity: float = 0.55
    ) -> list[IncidentSuggestion]:
        """Similarity search across *other* incidents (AI knowledge suggestions)."""
        incident = await self.get(incident_id)
        query = " ".join(filter(None, [incident.title, incident.description, incident.root_cause]))
        if not query.strip():
            return []
        matches = await self._memory.search(query, limit=30)

        by_incident: dict[uuid.UUID, list[float]] = defaultdict(list)
        for match in matches:
            if match.incident_id is not None and match.incident_id != incident_id:
                by_incident[match.incident_id].append(match.score)
        if not by_incident:
            return []

        this_services = await self._incident_services(incident_id)
        suggestions: list[IncidentSuggestion] = []
        for other_id, scores in by_incident.items():
            similarity = max(scores)
            if similarity < min_similarity:
                continue
            other = await self.get(other_id)
            other_services = await self._incident_services(other_id)
            shared = sorted(this_services & other_services)
            rationale = (
                f"This incident appears related to {other.reference} "
                f"({int(similarity * 100)}% similar"
                + (f"; shared services: {', '.join(shared)}" if shared else "")
                + ")."
            )
            suggestions.append(
                IncidentSuggestion(
                    incident_id=other_id,
                    reference=other.reference,
                    title=other.title,
                    similarity=round(similarity, 3),
                    shared_services=shared,
                    rationale=rationale,
                )
            )
        suggestions.sort(key=lambda s: s.similarity, reverse=True)
        return suggestions[:limit]

    async def link(
        self,
        source_id: uuid.UUID,
        target_id: uuid.UUID,
        *,
        reason: str | None = None,
        shared_services: list[str] | None = None,
        similarity: float = 0.0,
    ) -> IncidentLink:
        """Create a persistent incident↔incident link and a graph edge."""
        if source_id == target_id:
            raise ValidationFailedError("Cannot link an incident to itself", code="INVALID_LINK")
        source = await self.get(source_id)
        target = await self.get(target_id)
        async with self._session_factory() as session:
            existing = (
                await session.execute(
                    select(IncidentLink).where(
                        IncidentLink.source_id == source_id,
                        IncidentLink.target_id == target_id,
                    )
                )
            ).scalar_one_or_none()
            if existing is not None:
                return existing
            link = IncidentLink(
                source_id=source_id,
                target_id=target_id,
                reason=reason,
                shared_services=shared_services or [],
                similarity=similarity,
            )
            session.add(link)
            await session.commit()
            link_id = link.id
        await self._graph.upsert_edge(
            GraphEdge(
                source=f"incident:{source.title}",
                relation="related_to",
                target=f"incident:{target.title}",
            )
        )
        logger.info("Incidents linked source=%s target=%s", source.reference, target.reference)
        async with self._session_factory() as session:
            return (
                await session.execute(select(IncidentLink).where(IncidentLink.id == link_id))
            ).scalar_one()

    async def links(self, incident_id: uuid.UUID) -> list[IncidentLink]:
        """All links where this incident is the source."""
        async with self._session_factory() as session:
            return list(
                (
                    await session.execute(
                        select(IncidentLink).where(IncidentLink.source_id == incident_id)
                    )
                )
                .scalars()
                .all()
            )

    # --- Living documentation ------------------------------------------------

    async def regenerate_documentation(self, incident_id: uuid.UUID) -> dict[str, Any]:
        """Rebuild the incident's living documentation from all evidence."""
        bundle = await self._evidence_bundle(incident_id)
        documentation = generate_documentation(bundle)
        payload = documentation.model_dump_doc()
        async with self._session_factory() as session:
            incident = (
                await session.execute(select(Incident).where(Incident.id == incident_id))
            ).scalar_one()
            incident.documentation = payload
            incident.documentation_generated_at = datetime.now(UTC).replace(tzinfo=None)
            await session.commit()
        logger.info("Documentation regenerated incident_id=%s", incident_id)
        return payload

    async def evidence(self, incident_id: uuid.UUID) -> dict[str, list[Any]]:
        """Return the incident's documents, meetings, and experiences."""
        async with self._session_factory() as session:
            documents = (
                (await session.execute(select(Document).where(Document.incident_id == incident_id)))
                .scalars()
                .all()
            )
            meetings = (
                (await session.execute(select(Meeting).where(Meeting.incident_id == incident_id)))
                .scalars()
                .all()
            )
            experiences = (
                (
                    await session.execute(
                        select(OperationalExperience).where(
                            OperationalExperience.incident_id == incident_id
                        )
                    )
                )
                .scalars()
                .all()
            )
        return {
            "documents": list(documents),
            "meetings": list(meetings),
            "experiences": list(experiences),
        }

    # --- internals -----------------------------------------------------------

    async def _evidence_bundle(self, incident_id: uuid.UUID) -> EvidenceBundle:
        """Load everything needed to regenerate documentation."""
        async with self._session_factory() as session:
            incident = (
                await session.execute(select(Incident).where(Incident.id == incident_id))
            ).scalar_one()
            documents = list(
                (await session.execute(select(Document).where(Document.incident_id == incident_id)))
                .scalars()
                .all()
            )
            meetings = list(
                (await session.execute(select(Meeting).where(Meeting.incident_id == incident_id)))
                .scalars()
                .all()
            )
            experiences = list(
                (
                    await session.execute(
                        select(OperationalExperience).where(
                            OperationalExperience.incident_id == incident_id
                        )
                    )
                )
                .scalars()
                .all()
            )
            summaries: dict[str, Any] = {}
            for meeting in meetings:
                summary = (
                    await session.execute(
                        select(MeetingSummary).where(MeetingSummary.meeting_id == meeting.id)
                    )
                ).scalar_one_or_none()
                if summary is not None:
                    summaries[str(meeting.id)] = summary
        return EvidenceBundle(
            incident=incident,
            documents=documents,
            meetings=meetings,
            summaries=summaries,
            experiences=experiences,
        )

    async def _incident_services(self, incident_id: uuid.UUID) -> set[str]:
        """Service/technology names associated with an incident (from experiences)."""
        async with self._session_factory() as session:
            experiences = (
                (
                    await session.execute(
                        select(OperationalExperience).where(
                            OperationalExperience.incident_id == incident_id
                        )
                    )
                )
                .scalars()
                .all()
            )
        services: set[str] = set()
        for experience in experiences:
            services.update(str(t).lower() for t in experience.related_technologies or [])
        return services

    async def _project_document_graph(self, incident: Incident, content: str) -> None:
        """Project relationships found in an uploaded document into the graph."""
        normalized_relationships = extract_relationships
        for relationship in normalized_relationships(_fake_doc(incident.title, content), []):
            await self._graph.upsert_edge(
                GraphEdge(
                    source=relationship.source_name,
                    relation=relationship.relation,
                    target=relationship.target_name,
                )
            )
        for technology in extract_technologies(content):
            await self._graph.upsert_edge(
                GraphEdge(
                    source=f"incident:{incident.title}", relation="references", target=technology
                )
            )

    async def _append_incident_field(self, incident_id: uuid.UUID, field: str, value: str) -> None:
        """Append text to an incident free-text field (root cause, resolution, ...)."""
        async with self._session_factory() as session:
            incident = (
                await session.execute(select(Incident).where(Incident.id == incident_id))
            ).scalar_one()
            current = getattr(incident, field) or ""
            setattr(incident, field, f"{current}\n{value}".strip() if current else value)
            await session.commit()


def _fake_doc(title: str, content: str) -> Any:
    """Build a minimal NormalizedDocument for relationship extraction."""
    from opsmemory.processing.models import NormalizedDocument

    return NormalizedDocument(
        identifier=title,
        title=title,
        content=content,
        source=DocumentSource.USER,
    )
