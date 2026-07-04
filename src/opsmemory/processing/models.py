"""Internal representations used by the processing pipeline."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from opsmemory.domain.enums import DocumentSource


class RawContent(BaseModel):
    """Raw content fetched by a connector, before parsing."""

    identifier: str = Field(description="Stable source identifier (path or URL).")
    content: str
    content_type: str = Field(description='Format hint: "markdown", "html", "yaml", ...')
    url: str | None = None
    title_hint: str | None = None
    last_modified: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class NormalizedDocument(BaseModel):
    """Source-agnostic document produced by the parser stage.

    Downstream stages (chunking, relationships, memory construction) never
    need to know which connector produced a document.
    """

    identifier: str
    title: str
    content: str = Field(description="Cleaned plain-text/markdown content.")
    source: DocumentSource
    url: str | None = None
    author: str | None = None
    tags: list[str] = Field(default_factory=list)
    last_modified: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Chunk(BaseModel):
    """A semantically meaningful section of a document."""

    section: str = Field(description="Heading path, e.g. 'Deployment > Rollback'.")
    position: int
    content: str


class ExtractedRelationship(BaseModel):
    """A deterministic relationship discovered in document content."""

    source_name: str
    relation: str = Field(description="Edge type, e.g. depends_on, documented_by.")
    target_name: str
    target_kind: str = Field(default="service", description="Node kind of the target.")
