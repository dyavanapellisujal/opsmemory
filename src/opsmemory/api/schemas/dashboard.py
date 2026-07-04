"""Dashboard and global-assistant schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from opsmemory.agent.chat import Citation
from opsmemory.api.schemas.incidents import IncidentOut
from opsmemory.incidents.chat import RelatedIncident


class RecentItem(BaseModel):
    """A compact recent-activity entry."""

    id: uuid.UUID
    label: str
    detail: str | None = None
    at: datetime | None = None


class DashboardOut(BaseModel):
    """Dashboard summary of organizational memory."""

    total_incidents: int
    active_incidents: int
    total_memories: int
    total_meetings: int
    total_documents: int
    recent_incidents: list[IncidentOut] = Field(default_factory=list)
    recent_memories: list[RecentItem] = Field(default_factory=list)
    recent_meetings: list[RecentItem] = Field(default_factory=list)
    recent_documents: list[RecentItem] = Field(default_factory=list)


class AssistantRequest(BaseModel):
    """A question for the global AI assistant."""

    message: str = Field(min_length=2, max_length=8000)


class AssistantResponse(BaseModel):
    """A global assistant answer with related incidents and citations."""

    answer: str
    intent: str
    confidence: float
    citations: list[Citation] = Field(default_factory=list)
    related_incidents: list[RelatedIncident] = Field(default_factory=list)
    taught: bool = False
