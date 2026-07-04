"""Incident-hub request/response schemas."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from opsmemory.domain.enums import IncidentSeverity, IncidentStatus
from opsmemory.incidents.service import IncidentSuggestion


class IncidentCreate(BaseModel):
    """Create a new incident hub."""

    title: str = Field(min_length=1, max_length=500)
    description: str | None = None
    severity: IncidentSeverity = IncidentSeverity.SEV3
    status: IncidentStatus = IncidentStatus.OPEN


class IncidentUpdate(BaseModel):
    """Update incident metadata (documentation is never edited directly)."""

    title: str | None = None
    description: str | None = None
    severity: IncidentSeverity | None = None
    status: IncidentStatus | None = None
    root_cause: str | None = None
    resolution: str | None = None
    lessons_learned: str | None = None


class IncidentCounts(BaseModel):
    """Evidence counts shown on the incident card."""

    documents: int = 0
    meetings: int = 0
    memories: int = 0
    experiences: int = 0


class IncidentOut(BaseModel):
    """An incident card."""

    id: uuid.UUID
    reference: str
    number: int | None
    title: str
    description: str | None
    severity: IncidentSeverity
    status: IncidentStatus
    archived: bool
    created_at: datetime
    updated_at: datetime
    counts: IncidentCounts = Field(default_factory=IncidentCounts)

    model_config = {"from_attributes": True}


class EvidenceItem(BaseModel):
    """A piece of evidence attached to an incident."""

    kind: str
    id: uuid.UUID
    label: str
    detail: str | None = None
    url: str | None = None
    status: str | None = None


class IncidentLinkOut(BaseModel):
    """A stored incident↔incident relationship."""

    target_id: uuid.UUID
    reason: str | None
    shared_services: list[Any]
    similarity: float


class TimelineEventOut(BaseModel):
    """A single incident timeline event."""

    at: datetime
    kind: str
    label: str
    meeting_id: uuid.UUID | None = None


class IncidentDetailOut(IncidentOut):
    """Full incident: living documentation, evidence, links, suggestions, timeline."""

    root_cause: str | None = None
    resolution: str | None = None
    lessons_learned: str | None = None
    documentation: dict[str, Any] = Field(default_factory=dict)
    documentation_generated_at: datetime | None = None
    documents: list[EvidenceItem] = Field(default_factory=list)
    meetings: list[EvidenceItem] = Field(default_factory=list)
    experiences: list[EvidenceItem] = Field(default_factory=list)
    links: list[IncidentLinkOut] = Field(default_factory=list)
    suggestions: list[IncidentSuggestion] = Field(default_factory=list)
    timeline: list[TimelineEventOut] = Field(default_factory=list)


class DocumentUpload(BaseModel):
    """Upload a text document into an incident."""

    title: str = Field(min_length=1, max_length=500)
    content: str = Field(min_length=1)
    content_type: str = Field(default="markdown", description="markdown|html|yaml|json|text")


class ManualEntry(BaseModel):
    """A manual knowledge entry."""

    kind: str = Field(
        description="lesson|root_cause|resolution|architecture_decision"
        "|operational_experience|action_item"
    )
    content: str = Field(min_length=1)


class AttachMeeting(BaseModel):
    """Attach an existing meeting to an incident."""

    meeting_id: uuid.UUID


class IngestionOutcomeOut(BaseModel):
    """Result of a data-collection action, including AI suggestions."""

    incident_id: uuid.UUID
    memories_added: int
    suggestions: list[IncidentSuggestion]


class LinkRequest(BaseModel):
    """Accept an AI suggestion by linking two incidents."""

    target_id: uuid.UUID
    reason: str | None = None
    shared_services: list[str] = Field(default_factory=list)
    similarity: float = 0.0


class IncidentChatRequest(BaseModel):
    """A question scoped to a single incident."""

    message: str = Field(min_length=2, max_length=8000)


class ScopedAnswerOut(BaseModel):
    """An incident-scoped chat answer."""

    answer: str
    confidence: float
    citations: list[str]
