"""Incident entity: the central, continuously-enriched knowledge hub.

An Incident is not a ticket — it is the primary organizational-memory
object. Documents, meetings, memories, and operational experiences all link
back to an incident, and its living documentation is regenerated from that
evidence whenever anything changes (OpsMemory model).
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from opsmemory.db.base import Base, PortableJSON, PrimaryKeyMixin, TimestampMixin, portable_enum
from opsmemory.db.types import GUID
from opsmemory.domain.enums import IncidentSeverity, IncidentStatus

if TYPE_CHECKING:
    from opsmemory.db.models.document import Document
    from opsmemory.db.models.experience import OperationalExperience
    from opsmemory.db.models.meeting import Meeting
    from opsmemory.db.models.memory import Memory
    from opsmemory.db.models.team import Team


class Incident(Base, PrimaryKeyMixin, TimestampMixin):
    """A production incident and the knowledge hub that grows around it."""

    __tablename__ = "incidents"

    number: Mapped[int | None] = mapped_column(Integer(), unique=True, index=True)
    external_id: Mapped[str | None] = mapped_column(String(100), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(500), index=True)
    description: Mapped[str | None] = mapped_column(Text())
    severity: Mapped[IncidentSeverity] = mapped_column(portable_enum(IncidentSeverity), index=True)
    status: Mapped[IncidentStatus] = mapped_column(
        portable_enum(IncidentStatus), default=IncidentStatus.OPEN, index=True
    )
    archived: Mapped[bool] = mapped_column(Boolean(), default=False, index=True)
    root_cause: Mapped[str | None] = mapped_column(Text())
    resolution: Mapped[str | None] = mapped_column(Text())
    lessons_learned: Mapped[str | None] = mapped_column(Text())

    # Living documentation: regenerated from evidence, never hand-edited.
    documentation: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)
    documentation_generated_at: Mapped[datetime | None] = mapped_column()

    started_at: Mapped[datetime | None] = mapped_column()
    ended_at: Mapped[datetime | None] = mapped_column()

    team_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("teams.id"))
    team: Mapped["Team | None"] = relationship()

    experiences: Mapped[list["OperationalExperience"]] = relationship(back_populates="incident")
    documents: Mapped[list["Document"]] = relationship(back_populates="incident")
    memories: Mapped[list["Memory"]] = relationship(back_populates="incident")
    meetings: Mapped[list["Meeting"]] = relationship(back_populates="incident")

    @property
    def reference(self) -> str:
        """Human-facing incident code, e.g. ``INC-1042``."""
        return f"INC-{self.number}" if self.number is not None else f"INC-{str(self.id)[:8]}"

    def __repr__(self) -> str:
        return f"<Incident {self.reference} {self.title!r}>"


class IncidentLink(Base, PrimaryKeyMixin, TimestampMixin):
    """A discovered relationship between two incidents (AI suggestion accepted).

    Directed source → target with the rationale and shared-service citation
    the suggestion was based on; retrieval can traverse linked incidents.
    """

    __tablename__ = "incident_links"

    source_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("incidents.id", ondelete="CASCADE"), index=True
    )
    target_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("incidents.id", ondelete="CASCADE"), index=True
    )
    reason: Mapped[str | None] = mapped_column(Text())
    shared_services: Mapped[list[Any]] = mapped_column(PortableJSON, default=list)
    similarity: Mapped[float] = mapped_column(default=0.0)

    def __repr__(self) -> str:
        return f"<IncidentLink {self.source_id} -> {self.target_id}>"
