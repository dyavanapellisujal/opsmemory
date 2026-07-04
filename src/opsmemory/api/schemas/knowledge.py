"""Request/response schemas for knowledge APIs (connectors, search, chat, ...)."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from opsmemory.agent.chat import ChatResponse
from opsmemory.domain.enums import (
    ConnectorStatus,
    ConnectorType,
    IncidentSeverity,
    IncidentStatus,
    JobStatus,
)
from opsmemory.graph.store import GraphEdge
from opsmemory.memory.base import ScoredMemory
from opsmemory.retrieval.classifier import Intent
from opsmemory.retrieval.engine import DocumentEvidence, ExperienceEvidence, ServiceFact

__all__ = ["ChatResponse", "GraphEdge", "ScoredMemory"]


class ConnectorCreate(BaseModel):
    """Register a new knowledge source."""

    name: str = Field(min_length=1, max_length=200)
    type: ConnectorType
    config: dict[str, Any] = Field(
        default_factory=dict,
        description='Connector-specific config, e.g. {"path": "./docs"} or {"url": "https://..."}.',
    )


class ConnectorOut(BaseModel):
    """A configured connector."""

    id: uuid.UUID
    name: str
    type: ConnectorType
    config: dict[str, Any]
    status: ConnectorStatus
    enabled: bool
    last_sync_at: datetime | None

    model_config = {"from_attributes": True}


class ConnectorHealthOut(BaseModel):
    """Connector reachability check result."""

    healthy: bool
    message: str


class SyncAccepted(BaseModel):
    """Response to a sync trigger: poll the job for progress."""

    job_id: uuid.UUID
    status: JobStatus


class JobOut(BaseModel):
    """An ingestion job."""

    id: uuid.UUID
    connector_id: uuid.UUID
    status: JobStatus
    stats: dict[str, Any]
    error: str | None
    started_at: datetime | None
    finished_at: datetime | None

    model_config = {"from_attributes": True}


class DocumentOut(BaseModel):
    """A normalized engineering document (content omitted in lists)."""

    id: uuid.UUID
    title: str
    source: str
    url: str | None
    tags: list[Any]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DocumentDetailOut(DocumentOut):
    """Full document including content."""

    content: str
    extra: dict[str, Any]


class SearchRequest(BaseModel):
    """Hybrid search request."""

    query: str = Field(min_length=2, max_length=2000)


class SearchResponse(BaseModel):
    """Hybrid search results: the assembled evidence, without LLM reasoning."""

    query: str
    intent: Intent
    memories: list[ScoredMemory]
    documents: list[DocumentEvidence]
    experiences: list[ExperienceEvidence]
    services: list[ServiceFact]
    graph_facts: list[GraphEdge]


class ChatRequest(BaseModel):
    """Natural-language chat request."""

    message: str = Field(min_length=2, max_length=8000)
    author: str | None = None


class TeachRequest(BaseModel):
    """Teach OpsMemory a new operational experience."""

    content: str = Field(min_length=10, max_length=16000)
    author: str | None = None


class ExperienceOut(BaseModel):
    """A stored operational experience."""

    id: uuid.UUID
    problem: str
    symptoms: list[Any]
    root_cause: str | None
    resolution: str | None
    lessons_learned: str | None
    confidence: float
    source: str
    author: str | None
    related_technologies: list[Any]
    created_at: datetime

    model_config = {"from_attributes": True}


class ServiceOut(BaseModel):
    """A service with its ownership metadata."""

    id: uuid.UUID
    name: str
    description: str | None
    environment: str | None
    namespace: str | None
    owner_team: str | None = None

    model_config = {"from_attributes": True}


class TeamOut(BaseModel):
    """An engineering team."""

    id: uuid.UUID
    name: str
    description: str | None
    slack_channel: str | None

    model_config = {"from_attributes": True}


class IncidentOut(BaseModel):
    """An incident record."""

    id: uuid.UUID
    title: str
    severity: IncidentSeverity
    status: IncidentStatus
    root_cause: str | None
    resolution: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class RepositoryOut(BaseModel):
    """A repository record."""

    id: uuid.UUID
    name: str
    provider: str | None
    url: str | None

    model_config = {"from_attributes": True}


class GraphNeighborsOut(BaseModel):
    """Edges around an entity in the knowledge graph."""

    entity: str
    edges: list[GraphEdge]
