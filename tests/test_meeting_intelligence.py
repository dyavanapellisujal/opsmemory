"""Meeting Intelligence: meetings enrich incidents (existing + new-incident flows).

Recall is faked so the whole pipeline runs offline: create → webhook →
transcript download → extraction → incident resolve/create → enrich →
timeline + notifications → intelligent deletion.
"""

from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from opsmemory.db.models import Incident, Meeting, MeetingSummary, Memory, OperationalExperience
from opsmemory.domain.enums import MeetingStatus
from opsmemory.graph.kuzu_store import KuzuGraphStore
from opsmemory.incidents.service import IncidentService
from opsmemory.meetings.extraction import (
    IncidentExtraction,
    MeetingExtraction,
    OpExExtraction,
)
from opsmemory.memory.native import NativeMemoryEngine
from opsmemory.services.meetings import MeetingService
from opsmemory.services.notifications import NotificationService
from opsmemory.teaching.service import TeachingService

_TRANSCRIPT = [
    {
        "participant": {"name": "Alice"},
        "words": [{"text": "Redis"}, {"text": "auth"}, {"text": "failed"}],
    },
    {"participant": {"name": "Bob"}, "words": [{"text": "We"}, {"text": "rotated"}]},
]

_EXTRACTION = MeetingExtraction(
    meeting_summary="payments-api hit CrashLoopBackOff from a Redis auth failure.",
    incident=IncidentExtraction(
        title="Redis Authentication Failure Due to Expired Kubernetes Secret",
        severity="sev2",
        status="resolved",
        timeline=["14:30 alerts fired", "15:05 review"],
    ),
    services=["payments-api", "redis"],
    technologies=["kubernetes", "redis"],
    root_cause="The Kubernetes secret holding the Redis password expired.",
    resolution=["Rotate the secret", "Restart the deployment"],
    lessons_learned=["Alert on secret age before expiry"],
    architecture_decisions=["Adopt short-lived credentials"],
    operational_experience=OpExExtraction(
        problem="Redis authentication failed because the Kubernetes secret expired",
        resolution="Rotated the secret and restarted payments-api",
        lesson="Rotate credentials before expiry",
    ),
)


class FakeRecall:
    """In-memory Recall client: no network, deterministic transcript."""

    def __init__(self) -> None:
        self.counter = 0

    async def create_bot(self, meeting_url: str) -> dict[str, Any]:
        self.counter += 1
        return {"id": f"bot-{self.counter}"}

    async def get_bot(self, bot_id: str) -> dict[str, Any]:
        return {
            "recordings": [
                {
                    "media_shortcuts": {
                        "transcript": {"data": {"download_url": "https://recall/t"}},
                        "video_mixed": {"data": {"download_url": "https://recall/v"}},
                    }
                }
            ]
        }

    async def download_json(self, url: str) -> Any:
        return _TRANSCRIPT


class FakeLLM:
    """LLM stub returning the canned extraction JSON."""

    name = "fake"
    model = "fake-1"

    async def complete(self, system: str, user: str, *, max_tokens: int) -> str:
        return _EXTRACTION.model_dump_json()


@pytest.fixture
def meeting_service(
    session_factory: async_sessionmaker[AsyncSession],
    memory_engine: NativeMemoryEngine,
    graph_store: KuzuGraphStore,
) -> MeetingService:
    teaching = TeachingService(session_factory, memory_engine, graph_store, llm=None)
    incidents = IncidentService(session_factory, memory_engine, graph_store, teaching)
    notifications = NotificationService(session_factory)
    return MeetingService(
        session_factory,
        FakeRecall(),  # type: ignore[arg-type]
        FakeLLM(),
        memory_engine,
        graph_store,
        teaching,
        incidents,
        notifications,
    )


async def _run_meeting(service: MeetingService, meeting: Meeting) -> None:
    """Drive the webhook lifecycle to completion synchronously."""
    bot = {"data": {"bot": {"id": meeting.recall_bot_id}}}
    await service.handle_event("bot.in_call_recording", bot)
    # Run processing inline (not the background task) for deterministic asserts.
    await service.process(meeting.id)


async def test_new_incident_flow_autocreates_and_enriches(
    meeting_service: MeetingService,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    meeting = await meeting_service.create("https://meet.google.com/abc-defg-hij")
    assert meeting.incident_id is None  # deferred until AI names it

    await _run_meeting(meeting_service, meeting)

    async with session_factory() as session:
        refreshed = (
            await session.execute(select(Meeting).where(Meeting.id == meeting.id))
        ).scalar_one()
        assert refreshed.status is MeetingStatus.PROCESSED
        assert refreshed.incident_id is not None
        assert refreshed.transcript_downloaded and refreshed.summary_generated
        assert "Alice" in refreshed.participants

        incident = (
            await session.execute(select(Incident).where(Incident.id == refreshed.incident_id))
        ).scalar_one()
        # AI-generated engineering title, not "Meeting Summary".
        assert "Redis" in incident.title and "Secret" in incident.title
        assert incident.root_cause and "expired" in incident.root_cause.lower()

        experiences = (
            (
                await session.execute(
                    select(OperationalExperience).where(
                        OperationalExperience.incident_id == refreshed.incident_id
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(experiences) == 1
        memories = (
            (
                await session.execute(
                    select(Memory).where(Memory.incident_id == refreshed.incident_id)
                )
            )
            .scalars()
            .all()
        )
        assert len(memories) >= 1


async def test_existing_incident_flow_enriches_same_incident(
    meeting_service: MeetingService,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    incidents = IncidentService(
        session_factory,
        meeting_service._memory,  # type: ignore[attr-defined]
        meeting_service._graph,  # type: ignore[attr-defined]
        TeachingService(session_factory, meeting_service._memory, meeting_service._graph, None),  # type: ignore[attr-defined]
    )
    incident = await incidents.create("Existing Redis incident")

    meeting = await meeting_service.create(
        "https://zoom.us/j/123", title="Incident review", incident_id=incident.id
    )
    assert meeting.incident_id == incident.id
    await _run_meeting(meeting_service, meeting)

    # No NEW incident created — the meeting enriched the existing one.
    async with session_factory() as session:
        all_incidents = (await session.execute(select(Incident))).scalars().all()
        assert len(all_incidents) == 1

    detail = await incidents.get(incident.id)
    doc = await incidents.regenerate_documentation(incident.id)
    section_keys = {s["key"] for s in doc["sections"]}
    assert "timeline" in section_keys  # meeting timeline merged in
    counts = await incidents.counts(incident.id)
    assert counts["meetings"] == 1 and counts["memories"] >= 1

    timeline = await incidents.timeline(incident.id)
    kinds = {e.kind for e in timeline}
    assert {"meeting_scheduled", "transcript_processed", "documentation_updated"} <= kinds
    assert detail is not None


async def test_meeting_deletion_cascades_and_regenerates(
    meeting_service: MeetingService,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    meeting = await meeting_service.create("https://meet.google.com/xyz")
    await _run_meeting(meeting_service, meeting)
    incident_id = (await meeting_service.get(meeting.id)).incident_id
    assert incident_id is not None

    async with session_factory() as session:
        before = len((await session.execute(select(Memory))).scalars().all())
    assert before >= 1

    returned = await meeting_service.delete(meeting.id)
    assert returned == incident_id

    async with session_factory() as session:
        assert (
            await session.execute(select(Meeting).where(Meeting.id == meeting.id))
        ).scalar_one_or_none() is None
        summaries = (await session.execute(select(MeetingSummary))).scalars().all()
        assert summaries == []
        # Meeting-derived memories are gone.
        meeting_memories = [
            m
            for m in (await session.execute(select(Memory))).scalars().all()
            if (m.meta or {}).get("meeting_id") == str(meeting.id)
        ]
        assert meeting_memories == []


async def test_notifications_recorded(
    meeting_service: MeetingService,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    meeting = await meeting_service.create("https://meet.google.com/n")
    await _run_meeting(meeting_service, meeting)
    notifications = NotificationService(session_factory)
    items = await notifications.list()
    kinds = {n.kind for n in items}
    assert {"meeting_scheduled", "incident_created", "incident_enriched"} <= kinds
