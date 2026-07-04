"""Incident-hub endpoints: CRUD, data collection, suggestions, docs, chat.

All routes require authentication (when enabled) via ``CurrentUserDep``.
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, Query, UploadFile, status

from opsmemory.api.dependencies import (
    CurrentUserDep,
    IncidentChatServiceDep,
    IncidentServiceDep,
    MeetingServiceDep,
)
from opsmemory.api.schemas.incidents import (
    AttachMeeting,
    DocumentUpload,
    EvidenceItem,
    IncidentChatRequest,
    IncidentCounts,
    IncidentCreate,
    IncidentDetailOut,
    IncidentLinkOut,
    IncidentOut,
    IncidentUpdate,
    IngestionOutcomeOut,
    LinkRequest,
    ManualEntry,
    ScopedAnswerOut,
    TimelineEventOut,
)
from opsmemory.api.schemas.meetings import MeetingInvite, MeetingOut
from opsmemory.db.models import Incident, Meeting
from opsmemory.incidents.service import IncidentSuggestion
from opsmemory.processing.files import extract_upload

router = APIRouter(prefix="/incidents", tags=["incidents"])


async def _to_card(service: IncidentServiceDep, incident: Incident) -> IncidentOut:
    """Build an incident card with evidence counts."""
    card = IncidentOut.model_validate(incident)
    card.counts = IncidentCounts(**await service.counts(incident.id))
    return card


@router.get("", response_model=list[IncidentOut])
async def list_incidents(
    service: IncidentServiceDep,
    user: CurrentUserDep,
    include_archived: bool = Query(default=False),
) -> list[IncidentOut]:
    """List incidents (newest first) with evidence counts."""
    incidents = await service.list_incidents(include_archived=include_archived)
    return [await _to_card(service, incident) for incident in incidents]


@router.post("", response_model=IncidentOut, status_code=status.HTTP_201_CREATED)
async def create_incident(
    payload: IncidentCreate, service: IncidentServiceDep, user: CurrentUserDep
) -> IncidentOut:
    """Create a new incident knowledge hub."""
    incident = await service.create(
        payload.title,
        description=payload.description,
        severity=payload.severity,
        status=payload.status,
    )
    return await _to_card(service, incident)


@router.get("/{incident_id}", response_model=IncidentDetailOut)
async def get_incident(
    incident_id: uuid.UUID, service: IncidentServiceDep, user: CurrentUserDep
) -> IncidentDetailOut:
    """Return the full incident: documentation, evidence, links, suggestions."""
    incident = await service.get(incident_id)
    # Build explicitly: model_validate would lazy-load the ORM relationships
    # named like our evidence fields on a detached instance.
    detail = IncidentDetailOut(
        id=incident.id,
        reference=incident.reference,
        number=incident.number,
        title=incident.title,
        description=incident.description,
        severity=incident.severity,
        status=incident.status,
        archived=incident.archived,
        created_at=incident.created_at,
        updated_at=incident.updated_at,
        root_cause=incident.root_cause,
        resolution=incident.resolution,
        lessons_learned=incident.lessons_learned,
        documentation=incident.documentation or {},
        documentation_generated_at=incident.documentation_generated_at,
    )
    detail.counts = IncidentCounts(**await service.counts(incident_id))
    evidence = await service.evidence(incident_id)
    detail.documents = [
        EvidenceItem(kind="document", id=d.id, label=d.title, url=d.url)
        for d in evidence["documents"]
    ]
    detail.meetings = [
        EvidenceItem(
            kind="meeting",
            id=m.id,
            label=m.title or f"Meeting {str(m.id)[:8]}",
            url=m.recording_url,
            status=m.status.value,
        )
        for m in evidence["meetings"]
    ]
    detail.experiences = [
        EvidenceItem(kind="experience", id=e.id, label=e.problem, detail=e.resolution)
        for e in evidence["experiences"]
    ]
    detail.links = [
        IncidentLinkOut(
            target_id=link.target_id,
            reason=link.reason,
            shared_services=link.shared_services,
            similarity=link.similarity,
        )
        for link in await service.links(incident_id)
    ]
    detail.suggestions = await service.suggest_related(incident_id)
    detail.timeline = [
        TimelineEventOut(at=e.at, kind=e.kind, label=e.label, meeting_id=e.meeting_id)
        for e in await service.timeline(incident_id)
    ]
    return detail


@router.patch("/{incident_id}", response_model=IncidentOut)
async def update_incident(
    incident_id: uuid.UUID,
    payload: IncidentUpdate,
    service: IncidentServiceDep,
    user: CurrentUserDep,
) -> IncidentOut:
    """Update incident metadata; documentation is regenerated automatically."""
    incident = await service.update(incident_id, **payload.model_dump(exclude_none=True))
    return await _to_card(service, incident)


@router.post("/{incident_id}/archive", response_model=IncidentOut)
async def archive_incident(
    incident_id: uuid.UUID,
    service: IncidentServiceDep,
    user: CurrentUserDep,
    archived: bool = Query(default=True),
) -> IncidentOut:
    """Archive or restore an incident."""
    incident = await service.archive(incident_id, archived=archived)
    return await _to_card(service, incident)


@router.post(
    "/{incident_id}/documents",
    response_model=IngestionOutcomeOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    incident_id: uuid.UUID,
    payload: DocumentUpload,
    service: IncidentServiceDep,
    user: CurrentUserDep,
) -> IngestionOutcomeOut:
    """Add a document into the incident from pasted text (see /upload for files)."""
    author = user.email if user is not None else None
    outcome = await service.add_document(
        incident_id,
        title=payload.title,
        content=payload.content,
        content_type=payload.content_type,
        author=author,
    )
    return IngestionOutcomeOut(**outcome.model_dump())


@router.post(
    "/{incident_id}/documents/upload",
    response_model=IngestionOutcomeOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document_file(
    incident_id: uuid.UUID,
    service: IncidentServiceDep,
    user: CurrentUserDep,
    file: Annotated[UploadFile, File(description="Markdown, TXT, or PDF file.")],
    title: Annotated[str | None, Form()] = None,
) -> IngestionOutcomeOut:
    """Upload a real file (Markdown/TXT/PDF) into the incident; text is extracted."""
    data = await file.read()
    text, content_type = extract_upload(file.filename or "upload", data)
    author = user.email if user is not None else None
    outcome = await service.add_document(
        incident_id,
        title=title or (file.filename or "Uploaded document"),
        content=text,
        content_type=content_type,
        author=author,
    )
    return IngestionOutcomeOut(**outcome.model_dump())


@router.post(
    "/{incident_id}/knowledge",
    response_model=IngestionOutcomeOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_knowledge(
    incident_id: uuid.UUID,
    payload: ManualEntry,
    service: IncidentServiceDep,
    user: CurrentUserDep,
) -> IngestionOutcomeOut:
    """Add a manual knowledge entry to the incident."""
    author = user.email if user is not None else None
    outcome = await service.add_manual_knowledge(
        incident_id, kind=payload.kind, content=payload.content, author=author
    )
    return IngestionOutcomeOut(**outcome.model_dump())


@router.post("/{incident_id}/meetings", response_model=IngestionOutcomeOut)
async def attach_meeting(
    incident_id: uuid.UUID,
    payload: AttachMeeting,
    service: IncidentServiceDep,
    user: CurrentUserDep,
) -> IngestionOutcomeOut:
    """Attach an existing meeting's knowledge to the incident."""
    outcome = await service.attach_meeting(incident_id, payload.meeting_id)
    return IngestionOutcomeOut(**outcome.model_dump())


@router.post(
    "/{incident_id}/meetings/invite",
    response_model=MeetingOut,
    status_code=status.HTTP_201_CREATED,
)
async def invite_meeting(
    incident_id: uuid.UUID,
    payload: MeetingInvite,
    service: IncidentServiceDep,
    meetings: MeetingServiceDep,
    user: CurrentUserDep,
) -> Meeting:
    """Invite a Recall bot for this incident — the meeting will enrich it."""
    await service.get(incident_id)  # 404 if unknown
    return await meetings.create(
        payload.meeting_url,
        title=payload.title,
        organizer=payload.organizer,
        incident_id=incident_id,
    )


@router.get("/{incident_id}/suggestions", response_model=list[IncidentSuggestion])
async def suggestions(
    incident_id: uuid.UUID, service: IncidentServiceDep, user: CurrentUserDep
) -> list[IncidentSuggestion]:
    """Return AI-suggested related incidents."""
    return await service.suggest_related(incident_id)


@router.post("/{incident_id}/links", status_code=status.HTTP_201_CREATED)
async def link_incident(
    incident_id: uuid.UUID,
    payload: LinkRequest,
    service: IncidentServiceDep,
    user: CurrentUserDep,
) -> IncidentLinkOut:
    """Accept an AI suggestion: link this incident to another."""
    link = await service.link(
        incident_id,
        payload.target_id,
        reason=payload.reason,
        shared_services=payload.shared_services,
        similarity=payload.similarity,
    )
    return IncidentLinkOut(
        target_id=link.target_id,
        reason=link.reason,
        shared_services=link.shared_services,
        similarity=link.similarity,
    )


@router.post("/{incident_id}/documentation/regenerate")
async def regenerate_documentation(
    incident_id: uuid.UUID, service: IncidentServiceDep, user: CurrentUserDep
) -> dict[str, Any]:
    """Force-regenerate the incident's living documentation."""
    return await service.regenerate_documentation(incident_id)


@router.post("/{incident_id}/chat", response_model=ScopedAnswerOut)
async def incident_chat(
    incident_id: uuid.UUID,
    payload: IncidentChatRequest,
    chat: IncidentChatServiceDep,
    user: CurrentUserDep,
) -> ScopedAnswerOut:
    """Ask a question scoped to this incident's knowledge only."""
    answer = await chat.chat(incident_id, payload.message)
    return ScopedAnswerOut(**answer.model_dump())
