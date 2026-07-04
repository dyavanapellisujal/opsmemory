"""Memory entity: the primary semantic retrieval object.

A memory is an embedded, retrievable unit of knowledge — a document chunk,
an operational experience, or a synthesized summary — always traceable back
to its origin (PRD "Memory Traceability").
"""

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import Float, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from opsmemory.db.base import Base, PortableJSON, PrimaryKeyMixin, TimestampMixin, portable_enum
from opsmemory.db.types import GUID, PortableVector
from opsmemory.domain.enums import MemoryKind

if TYPE_CHECKING:
    from opsmemory.db.models.document import Document
    from opsmemory.db.models.experience import OperationalExperience
    from opsmemory.db.models.incident import Incident


class Memory(Base, PrimaryKeyMixin, TimestampMixin):
    """An embedded semantic memory (chunk, experience, or summary)."""

    __tablename__ = "memories"
    __table_args__ = (
        # ANN index for semantic search on PostgreSQL (ignored kwargs elsewhere).
        Index(
            "ix_memories_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    kind: Mapped[MemoryKind] = mapped_column(portable_enum(MemoryKind), index=True)
    content: Mapped[str] = mapped_column(Text())
    section: Mapped[str | None] = mapped_column(String(500))
    embedding: Mapped[list[float] | None] = mapped_column(PortableVector())
    embedding_model: Mapped[str | None] = mapped_column(String(100))
    confidence: Mapped[float] = mapped_column(Float(), default=0.5)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    meta: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)

    document_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    document: Mapped["Document | None"] = relationship()

    experience_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("operational_experiences.id", ondelete="CASCADE"), index=True
    )
    experience: Mapped["OperationalExperience | None"] = relationship()

    incident_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("incidents.id", ondelete="CASCADE"), index=True
    )
    incident: Mapped["Incident | None"] = relationship(back_populates="memories")

    def __repr__(self) -> str:
        return f"<Memory kind={self.kind} section={self.section!r}>"
