"""Dashboard and global AI assistant endpoints."""

from fastapi import APIRouter
from sqlalchemy import func, select

from opsmemory.api.dependencies import (
    ChatServiceDep,
    CurrentUserDep,
    IncidentChatServiceDep,
    IncidentServiceDep,
    SessionDep,
)
from opsmemory.api.schemas.dashboard import (
    AssistantRequest,
    AssistantResponse,
    DashboardOut,
    RecentItem,
)
from opsmemory.api.schemas.incidents import IncidentCounts, IncidentOut
from opsmemory.db.models import Document, Incident, Meeting, Memory
from opsmemory.domain.enums import IncidentStatus

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard", response_model=DashboardOut)
async def dashboard(
    session: SessionDep, service: IncidentServiceDep, user: CurrentUserDep
) -> DashboardOut:
    """Summarize organizational memory for the dashboard home."""

    async def scalar(stmt) -> int:  # type: ignore[no-untyped-def]
        return int((await session.execute(stmt)).scalar_one())

    total_incidents = await scalar(select(func.count()).select_from(Incident))
    active_incidents = await scalar(
        select(func.count()).select_from(Incident).where(Incident.status != IncidentStatus.RESOLVED)
    )
    total_memories = await scalar(select(func.count()).select_from(Memory))
    total_meetings = await scalar(select(func.count()).select_from(Meeting))
    total_documents = await scalar(select(func.count()).select_from(Document))

    incidents = (
        (
            await session.execute(
                select(Incident)
                .where(Incident.archived.is_(False))
                .order_by(Incident.updated_at.desc())
                .limit(5)
            )
        )
        .scalars()
        .all()
    )
    recent_incidents = []
    for incident in incidents:
        card = IncidentOut.model_validate(incident)
        card.counts = IncidentCounts(**await service.counts(incident.id))
        recent_incidents.append(card)

    memories = (
        (await session.execute(select(Memory).order_by(Memory.created_at.desc()).limit(5)))
        .scalars()
        .all()
    )
    meetings = (
        (await session.execute(select(Meeting).order_by(Meeting.created_at.desc()).limit(5)))
        .scalars()
        .all()
    )
    documents = (
        (await session.execute(select(Document).order_by(Document.created_at.desc()).limit(5)))
        .scalars()
        .all()
    )

    return DashboardOut(
        total_incidents=total_incidents,
        active_incidents=active_incidents,
        total_memories=total_memories,
        total_meetings=total_meetings,
        total_documents=total_documents,
        recent_incidents=recent_incidents,
        recent_memories=[
            RecentItem(
                id=m.id, label=(m.section or m.kind.value), detail=m.content[:120], at=m.created_at
            )
            for m in memories
        ],
        recent_meetings=[
            RecentItem(id=m.id, label=m.title or "Meeting", detail=m.status.value, at=m.created_at)
            for m in meetings
        ],
        recent_documents=[
            RecentItem(id=d.id, label=d.title, detail=d.source.value, at=d.created_at)
            for d in documents
        ],
    )


@router.post("/assistant", response_model=AssistantResponse)
async def assistant(
    payload: AssistantRequest,
    chat: ChatServiceDep,
    incident_chat: IncidentChatServiceDep,
    user: CurrentUserDep,
) -> AssistantResponse:
    """Global AI assistant: reason across all incidents and cite related ones."""
    author = user.email if user is not None else None
    response = await chat.chat(payload.message, author=author)
    related = await incident_chat.related_incidents(payload.message)
    return AssistantResponse(
        answer=response.answer,
        intent=response.intent.value,
        confidence=response.confidence,
        citations=response.citations,
        related_incidents=related,
        taught=response.taught,
    )
