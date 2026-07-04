"""Document entity: any source of engineering knowledge."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from opsmemory.db.base import Base, PortableJSON, PrimaryKeyMixin, TimestampMixin, portable_enum
from opsmemory.db.types import GUID
from opsmemory.domain.enums import DocumentSource

if TYPE_CHECKING:
    from opsmemory.db.models.connector import Connector
    from opsmemory.db.models.incident import Incident
    from opsmemory.db.models.repository import Repository


class Document(Base, PrimaryKeyMixin, TimestampMixin):
    """A normalized engineering document (README, runbook, ADR, wiki page, ...).

    Documents preserve the original content verbatim (Layer 1 — Raw
    Knowledge). Derived artifacts such as chunks, embeddings, and memories
    always reference back to their parent document for traceability.
    """

    __tablename__ = "documents"

    title: Mapped[str] = mapped_column(String(500), index=True)
    description: Mapped[str | None] = mapped_column(Text())
    source: Mapped[DocumentSource] = mapped_column(portable_enum(DocumentSource), index=True)
    url: Mapped[str | None] = mapped_column(String(2000))
    author: Mapped[str | None] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text())
    summary: Mapped[str | None] = mapped_column(Text())
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    tags: Mapped[list[Any]] = mapped_column(PortableJSON, default=list)
    extra: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)
    last_modified: Mapped[datetime | None] = mapped_column()

    repository_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("repositories.id"))
    repository: Mapped["Repository | None"] = relationship(back_populates="documents")

    connector_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("connectors.id"))
    connector: Mapped["Connector | None"] = relationship(back_populates="documents")

    incident_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("incidents.id", ondelete="SET NULL"), index=True
    )
    incident: Mapped["Incident | None"] = relationship(back_populates="documents")

    def __repr__(self) -> str:
        return f"<Document {self.title!r} source={self.source}>"
