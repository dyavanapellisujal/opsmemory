"""Meeting Intelligence: meetings are evidence that enrich incident memory.

A meeting is never a standalone object — it exists to enrich an Incident
(Synapse model). Two flows:

* **Existing incident** — the meeting is invited with ``incident_id`` set and
  becomes another knowledge source for that incident.
* **New incident** — the meeting is invited with no incident; after the
  transcript is processed the AI generates a title/severity/summary and a new
  Incident is created automatically, then enriched.

Webhook → immediate ack. ``bot.done`` queues a background pipeline whose
stages are independently retried and idempotent: download transcript →
extract knowledge → resolve/create incident → enrich (experience, memories,
graph, living documentation) → timeline + notifications. Deleting a meeting
intelligently removes its transcript, summary, memories, experiences, and
graph traces, then regenerates the incident's documentation.
"""

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from opsmemory.ai.base import LLMProvider
from opsmemory.connectors.recall import (
    RecallClient,
    infer_provider,
    recording_download_url,
    render_transcript,
    transcript_download_url,
    transcript_participants,
)
from opsmemory.core.errors import NotFoundError, OpsMemoryError
from opsmemory.core.logging import get_logger
from opsmemory.core.retry import retry_async
from opsmemory.db.models import (
    Incident,
    Meeting,
    MeetingSummary,
    MeetingTranscript,
    OperationalExperience,
)
from opsmemory.domain.enums import (
    ExperienceSource,
    IncidentSeverity,
    IncidentStatus,
    MeetingProvider,
    MeetingStatus,
    MemoryKind,
)
from opsmemory.graph.store import GraphEdge, GraphStore
from opsmemory.incidents.service import IncidentService
from opsmemory.meetings.extraction import MeetingExtraction, extract_incident_knowledge
from opsmemory.memory.base import MemoryEngine, MemoryItem
from opsmemory.services.notifications import NotificationService
from opsmemory.teaching.service import ExtractedExperience, TeachingService

logger = get_logger(__name__)


class MeetingService:
    """Turns finished meetings into enriched incident memory."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        recall: RecallClient | None,
        llm: LLMProvider | None,
        memory_engine: MemoryEngine,
        graph: GraphStore,
        teaching: TeachingService,
        incidents: IncidentService,
        notifications: NotificationService,
        llm_max_tokens: int = 4096,
    ) -> None:
        self._session_factory = session_factory
        self._recall = recall
        self._llm = llm
        self._memory = memory_engine
        self._graph = graph
        self._teaching = teaching
        self._incidents = incidents
        self._notify = notifications
        self._llm_max_tokens = llm_max_tokens
        self._tasks: set[asyncio.Task[None]] = set()

    # ------------------------------------------------------------------ create

    async def create(
        self,
        meeting_url: str,
        *,
        title: str | None = None,
        provider: MeetingProvider | None = None,
        organizer: str | None = None,
        incident_id: uuid.UUID | None = None,
    ) -> Meeting:
        """Invite a Recall bot. ``incident_id`` set → enrich it; unset → new incident later.

        Raises:
            OpsMemoryError: If Recall is not configured, or the incident is unknown.
        """
        if self._recall is None:
            raise OpsMemoryError(
                "Meeting connector is not configured — set OPSMEMORY_RECALL_API_KEY",
                code="RECALL_NOT_CONFIGURED",
                status_code=503,
            )
        if incident_id is not None:
            await self._incidents.get(incident_id)  # 404 if unknown
        bot = await self._recall.create_bot(meeting_url)
        async with self._session_factory() as session:
            meeting = Meeting(
                recall_bot_id=str(bot["id"]),
                meeting_url=meeting_url,
                provider=provider or infer_provider(meeting_url),
                title=title,
                organizer=organizer,
                status=MeetingStatus.SCHEDULED,
                incident_id=incident_id,
            )
            session.add(meeting)
            await session.commit()
            meeting_id = meeting.id
        logger.info(
            "Meeting created meeting_id=%s bot_id=%s incident_id=%s",
            meeting_id,
            bot["id"],
            incident_id,
        )
        if incident_id is not None:
            await self._incidents.add_event(
                incident_id,
                kind="meeting_scheduled",
                label=f"Meeting bot invited: {title or meeting_url}",
                meeting_id=meeting_id,
            )
        await self._notify.notify(
            "meeting_scheduled",
            f"Meeting bot invited{' to ' + (title or '') if title else ''}",
            incident_id=incident_id,
        )
        return await self.get(meeting_id)

    async def get(self, meeting_id: uuid.UUID) -> Meeting:
        """Fetch a meeting row or raise 404."""
        async with self._session_factory() as session:
            meeting = (
                await session.execute(select(Meeting).where(Meeting.id == meeting_id))
            ).scalar_one_or_none()
            if meeting is None:
                raise NotFoundError(f"Meeting {meeting_id} not found", code="MEETING_NOT_FOUND")
            return meeting

    # ----------------------------------------------------------------- webhook

    async def handle_event(self, event: str, payload: dict[str, Any]) -> bool:
        """Handle a Recall webhook event; ``bot.done`` queues async processing."""
        bot_id = str(((payload.get("data") or {}).get("bot") or {}).get("id") or "")
        if not bot_id:
            return False
        async with self._session_factory() as session:
            meeting = (
                await session.execute(select(Meeting).where(Meeting.recall_bot_id == bot_id))
            ).scalar_one_or_none()
            if meeting is None:
                logger.warning("Webhook for unknown bot_id=%s (event=%s)", bot_id, event)
                return False
            meeting_id = meeting.id
            incident_id = meeting.incident_id

            if event == "bot.in_call_recording":
                meeting.status = MeetingStatus.RECORDING
                meeting.started_at = meeting.started_at or _now()
                await session.commit()
                logger.info("Meeting started meeting_id=%s", meeting_id)
            elif event == "bot.fatal":
                meeting.status = MeetingStatus.FAILED
                await session.commit()
                logger.error("Meeting failed meeting_id=%s (bot.fatal)", meeting_id)
            elif event in ("bot.done", "bot.call_ended"):
                meeting.status = MeetingStatus.COMPLETED
                meeting.ended_at = meeting.ended_at or _now()
                await session.commit()
                logger.info("Meeting completed meeting_id=%s", meeting_id)

        if event in ("bot.done", "bot.call_ended") and incident_id is not None:
            await self._incidents.add_event(
                incident_id,
                kind="meeting_ended",
                label="Incident review meeting ended",
                meeting_id=meeting_id,
            )
        if event == "bot.done":
            await self._notify.notify(
                "meeting_finished",
                "Meeting finished — processing transcript",
                incident_id=incident_id,
            )
            self._schedule_processing(meeting_id)
        return True

    def _schedule_processing(self, meeting_id: uuid.UUID) -> None:
        """Run the knowledge pipeline as a tracked background task."""
        task = asyncio.create_task(self._process_safely(meeting_id))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _process_safely(self, meeting_id: uuid.UUID) -> None:
        """Wrapper so a failed pipeline marks the meeting instead of raising."""
        try:
            await self.process(meeting_id)
        except Exception as exc:
            logger.exception("Meeting processing failed meeting_id=%s", meeting_id)
            await self._update(meeting_id, status=MeetingStatus.FAILED, error=str(exc)[:2000])

    # ---------------------------------------------------------------- pipeline

    async def process(self, meeting_id: uuid.UUID) -> None:
        """Post-meeting pipeline: transcript → extract → resolve incident → enrich."""
        transcript = await retry_async(
            lambda: self._download_transcript(meeting_id),
            label=f"transcript-download meeting_id={meeting_id}",
        )
        extraction = await retry_async(
            lambda: self._extract_knowledge(meeting_id, transcript),
            label=f"incident-extraction meeting_id={meeting_id}",
        )
        incident_id = await retry_async(
            lambda: self._resolve_incident(meeting_id, extraction),
            label=f"incident-resolve meeting_id={meeting_id}",
        )
        await retry_async(
            lambda: self._enrich_incident(meeting_id, incident_id, extraction),
            label=f"incident-enrich meeting_id={meeting_id}",
        )
        await self._update(meeting_id, status=MeetingStatus.PROCESSED)

    async def _download_transcript(self, meeting_id: uuid.UUID) -> str:
        """Stage 1: download and store the raw transcript (skips when present)."""
        async with self._session_factory() as session:
            existing = (
                await session.execute(
                    select(MeetingTranscript).where(MeetingTranscript.meeting_id == meeting_id)
                )
            ).scalar_one_or_none()
            if existing is not None:
                return existing.transcript
            meeting = (
                await session.execute(select(Meeting).where(Meeting.id == meeting_id))
            ).scalar_one()
            bot_id = meeting.recall_bot_id

        assert self._recall is not None  # processing only starts via a created bot
        bot = await self._recall.get_bot(bot_id)
        url = transcript_download_url(bot)
        if not url:
            raise OpsMemoryError(
                f"No transcript available yet for bot {bot_id}", code="TRANSCRIPT_UNAVAILABLE"
            )
        raw = await self._recall.download_json(url)
        text = render_transcript(raw)
        if not text.strip():
            raise OpsMemoryError(f"Transcript for bot {bot_id} is empty", code="TRANSCRIPT_EMPTY")
        participants = transcript_participants(raw)

        async with self._session_factory() as session:
            meeting = (
                await session.execute(select(Meeting).where(Meeting.id == meeting_id))
            ).scalar_one()
            session.add(
                MeetingTranscript(
                    meeting_id=meeting_id, transcript=text, token_count=max(1, len(text) // 4)
                )
            )
            meeting.transcript_url = url
            meeting.recording_url = recording_download_url(bot)
            meeting.transcript_downloaded = True
            meeting.participants = participants
            if meeting.started_at and meeting.ended_at:
                meeting.duration_seconds = int(
                    (meeting.ended_at - meeting.started_at).total_seconds()
                )
            incident_id = meeting.incident_id
            await session.commit()
        logger.info("Transcript downloaded meeting_id=%s (%d chars)", meeting_id, len(text))
        if incident_id is not None:
            await self._incidents.add_event(
                incident_id,
                kind="transcript_processed",
                label="Meeting transcript downloaded",
                meeting_id=meeting_id,
            )
        await self._notify.notify("transcript_ready", "Transcript ready", incident_id=incident_id)
        return text

    async def _extract_knowledge(self, meeting_id: uuid.UUID, transcript: str) -> MeetingExtraction:
        """Stage 2: LLM incident extraction with the dedicated SRE prompt."""
        async with self._session_factory() as session:
            existing = (
                await session.execute(
                    select(MeetingSummary).where(MeetingSummary.meeting_id == meeting_id)
                )
            ).scalar_one_or_none()
            if existing is not None:
                return MeetingExtraction.model_validate(existing.structured_json)

        extraction = await extract_incident_knowledge(
            self._llm, transcript, max_tokens=self._llm_max_tokens
        )
        async with self._session_factory() as session:
            meeting = (
                await session.execute(select(Meeting).where(Meeting.id == meeting_id))
            ).scalar_one()
            session.add(
                MeetingSummary(
                    meeting_id=meeting_id,
                    summary=extraction.meeting_summary,
                    structured_json=extraction.model_dump(mode="json"),
                )
            )
            meeting.summary_generated = True
            await session.commit()
        logger.info("Summary generated meeting_id=%s", meeting_id)
        return extraction

    async def _resolve_incident(
        self, meeting_id: uuid.UUID, extraction: MeetingExtraction
    ) -> uuid.UUID:
        """Stage 3: use the meeting's incident, or create one from the extraction."""
        meeting = await self.get(meeting_id)
        if meeting.incident_id is not None:
            return meeting.incident_id

        title = _incident_title(extraction)
        severity = (
            extraction.incident.severity_enum()
            if extraction.incident is not None
            else IncidentSeverity.SEV3
        )
        status = extraction.incident.status_enum() if extraction.incident is not None else None
        incident = await self._incidents.create(
            title,
            description=extraction.meeting_summary or None,
            severity=severity,
            status=status or IncidentStatus.OPEN,
        )
        async with self._session_factory() as session:
            row = (
                await session.execute(select(Meeting).where(Meeting.id == meeting_id))
            ).scalar_one()
            row.incident_id = incident.id
            await session.commit()
        await self._incidents.add_event(
            incident.id,
            kind="incident_created",
            label=f"Incident auto-created from meeting: {title}",
            meeting_id=meeting_id,
        )
        await self._notify.notify(
            "incident_created", f"New incident created: {title}", incident_id=incident.id
        )
        logger.info("Incident auto-created incident_id=%s meeting_id=%s", incident.id, meeting_id)
        return incident.id

    async def _enrich_incident(
        self, meeting_id: uuid.UUID, incident_id: uuid.UUID, extraction: MeetingExtraction
    ) -> None:
        """Stage 4: experience, memories, graph, scalar merge, docs, timeline."""
        meeting = await self.get(meeting_id)
        await self._merge_incident_fields(incident_id, extraction)
        await self._store_experience(meeting, incident_id, extraction)
        await self._store_memories(meeting, incident_id, extraction)
        await self._project_graph(meeting, incident_id, extraction)
        await self._update(meeting_id, cognee_synced=True)
        # Living documentation re-derives from all evidence (intelligent merge).
        await self._incidents.regenerate_documentation(incident_id)
        await self._incidents.add_event(
            incident_id,
            kind="experience_learned",
            label="Operational experience learned from meeting",
            meeting_id=meeting_id,
        )
        await self._incidents.add_event(
            incident_id,
            kind="documentation_updated",
            label="Incident documentation regenerated",
            meeting_id=meeting_id,
        )
        await self._notify.notify(
            "incident_enriched",
            "Incident enriched from meeting — documentation & memory updated",
            incident_id=incident_id,
        )
        logger.info(
            "Cognee synced + docs updated meeting_id=%s incident_id=%s (engine=%s)",
            meeting_id,
            incident_id,
            self._memory.name,
        )

    async def _merge_incident_fields(
        self, incident_id: uuid.UUID, extraction: MeetingExtraction
    ) -> None:
        """Intelligently merge scalar fields — fill blanks, append new content."""
        async with self._session_factory() as session:
            incident = (
                await session.execute(select(Incident).where(Incident.id == incident_id))
            ).scalar_one()
            incident.root_cause = _merge_text(incident.root_cause, extraction.root_cause)
            incident.resolution = _merge_text(
                incident.resolution, "\n".join(extraction.resolution) or None
            )
            incident.lessons_learned = _merge_text(
                incident.lessons_learned, "\n".join(extraction.lessons_learned) or None
            )
            await session.commit()

    async def _store_experience(
        self, meeting: Meeting, incident_id: uuid.UUID, extraction: MeetingExtraction
    ) -> None:
        """Create/reinforce the operational experience via the Teaching Pipeline."""
        exp = extraction.operational_experience
        if exp is None or not (exp.problem or "").strip():
            return
        assert exp.problem is not None
        await self._teaching.teach(
            exp.problem,
            author=f"meeting:{meeting.id}",
            source=ExperienceSource.MEETING,
            incident_id=incident_id,
            extracted=ExtractedExperience(
                problem=exp.problem,
                root_cause=extraction.root_cause,
                resolution=exp.resolution,
                lessons_learned=exp.lesson,
            ),
        )

    async def _store_memories(
        self, meeting: Meeting, incident_id: uuid.UUID, extraction: MeetingExtraction
    ) -> None:
        """Store structured knowledge (never the raw transcript) as incident memories."""
        meta_base = {"meeting_id": str(meeting.id), "meeting_title": meeting.title or ""}
        items: list[MemoryItem] = []

        def add(category: str, content: str) -> None:
            if content.strip():
                items.append(
                    MemoryItem(
                        kind=MemoryKind.SUMMARY,
                        content=content.strip(),
                        section=f"meeting:{category}",
                        confidence=0.65,
                        incident_id=incident_id,
                        meta={**meta_base, "category": category},
                    )
                )

        title = meeting.title or "engineering meeting"
        add("summary", f"Meeting summary ({title}): {extraction.meeting_summary}")
        if extraction.root_cause:
            add("root_cause", f"Root cause ({title}): {extraction.root_cause}")
        if extraction.lessons_learned:
            add("lessons_learned", f"Lessons ({title}): " + "; ".join(extraction.lessons_learned))
        for decision in extraction.architecture_decisions:
            add("architecture_decision", f"Architecture decision ({title}): {decision}")
        actions = [
            f"{i.owner or 'unassigned'}: {i.task}" for i in extraction.action_items if i.task
        ]
        if actions:
            add("action_items", f"Action items ({title}): " + "; ".join(actions))
        await self._memory.add(items)

    async def _project_graph(
        self, meeting: Meeting, incident_id: uuid.UUID, extraction: MeetingExtraction
    ) -> None:
        """Project meeting → incident → service/experience relationships."""
        async with self._session_factory() as session:
            incident = (
                await session.execute(select(Incident).where(Incident.id == incident_id))
            ).scalar_one()
            incident_node = f"incident:{incident.title}"
        meeting_node = f"meeting:{meeting.title or meeting.id}"
        edges: list[GraphEdge] = [
            GraphEdge(source=meeting_node, relation="generated", target=incident_node)
        ]
        edges += [
            GraphEdge(source=incident_node, relation="affects", target=s)
            for s in extraction.services
        ]
        edges += [
            GraphEdge(source=incident_node, relation="references", target=t)
            for t in extraction.technologies
        ]
        exp = extraction.operational_experience
        if exp is not None and exp.problem:
            exp_node = f"experience:{exp.problem[:80]}"
            edges.append(GraphEdge(source=exp_node, relation="related_to", target=incident_node))
            edges += [
                GraphEdge(source=exp_node, relation="related_to", target=s)
                for s in extraction.services
            ]
        for edge in edges:
            await self._graph.upsert_edge(edge)

    # ---------------------------------------------------------------- deletion

    async def delete(self, meeting_id: uuid.UUID) -> uuid.UUID | None:
        """Intelligently delete a meeting and everything derived from it.

        Removes transcript, summary, meeting memories, meeting-derived
        experiences, and graph traces, then regenerates the incident's
        documentation from the remaining evidence.

        Returns:
            The affected incident id (for the caller to refresh), or None.
        """
        meeting = await self.get(meeting_id)
        incident_id = meeting.incident_id
        meeting_title = meeting.title or str(meeting_id)

        await self._memory.delete_for_meeting(meeting_id)

        async with self._session_factory() as session:
            experiences = (
                (
                    await session.execute(
                        select(OperationalExperience).where(
                            OperationalExperience.author == f"meeting:{meeting_id}"
                        )
                    )
                )
                .scalars()
                .all()
            )
            for experience in experiences:
                await self._memory.delete_for_experience(experience.id)
                await session.delete(experience)
            # Transcript + summary cascade via FK, but delete explicitly to be safe.
            transcript = (
                await session.execute(
                    select(MeetingTranscript).where(MeetingTranscript.meeting_id == meeting_id)
                )
            ).scalar_one_or_none()
            summary = (
                await session.execute(
                    select(MeetingSummary).where(MeetingSummary.meeting_id == meeting_id)
                )
            ).scalar_one_or_none()
            for row in (transcript, summary):
                if row is not None:
                    await session.delete(row)
            row_meeting = (
                await session.execute(select(Meeting).where(Meeting.id == meeting_id))
            ).scalar_one()
            await session.delete(row_meeting)
            await session.commit()

        await self._graph.delete_node(f"meeting:{meeting_title}")
        for experience in experiences:
            await self._graph.delete_node(f"experience:{experience.problem[:80]}")

        if incident_id is not None:
            await self._incidents.regenerate_documentation(incident_id)
            await self._incidents.add_event(
                incident_id,
                kind="meeting_removed",
                label=f"Meeting removed and documentation recomputed: {meeting_title}",
            )
            await self._notify.notify(
                "documentation_updated",
                "Meeting deleted — incident documentation recomputed",
                incident_id=incident_id,
            )
        logger.info("Meeting deleted meeting_id=%s incident_id=%s", meeting_id, incident_id)
        return incident_id

    async def _update(self, meeting_id: uuid.UUID, **fields: Any) -> None:
        """Apply field updates to a meeting row."""
        async with self._session_factory() as session:
            meeting = (
                await session.execute(select(Meeting).where(Meeting.id == meeting_id))
            ).scalar_one()
            for key, value in fields.items():
                setattr(meeting, key, value)
            await session.commit()


def _incident_title(extraction: MeetingExtraction) -> str:
    """Pick a concise engineering incident title from the extraction."""
    if extraction.incident is not None and extraction.incident.title.strip():
        return extraction.incident.title.strip()[:200]
    exp = extraction.operational_experience
    if exp is not None and (exp.problem or "").strip():
        return (exp.problem or "").strip()[:200]
    if extraction.root_cause:
        return extraction.root_cause.strip()[:200]
    if extraction.meeting_summary:
        return extraction.meeting_summary.strip()[:120]
    return "Untitled engineering incident"


def _merge_text(current: str | None, incoming: str | None) -> str | None:
    """Fill a blank field or append genuinely new content (never overwrite)."""
    incoming = (incoming or "").strip()
    if not incoming:
        return current
    if not current:
        return incoming
    if incoming.lower() in current.lower():
        return current
    return f"{current}\n{incoming}"


def _now() -> datetime:
    """Naive UTC timestamp for DateTime columns."""
    return datetime.now(UTC).replace(tzinfo=None)
