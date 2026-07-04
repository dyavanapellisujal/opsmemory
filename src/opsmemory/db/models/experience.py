"""Operational Experience entity: engineering knowledge learned from real problems.

Operational Experiences are the highest-value entities in OpsMemory: unlike
static documentation, they continue to evolve as engineers contribute new
lessons.
"""

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from opsmemory.db.base import Base, PortableJSON, PrimaryKeyMixin, TimestampMixin, portable_enum
from opsmemory.db.types import GUID
from opsmemory.domain.enums import ExperienceSource

if TYPE_CHECKING:
    from opsmemory.db.models.incident import Incident


class OperationalExperience(Base, PrimaryKeyMixin, TimestampMixin):
    """A structured operational lesson (problem → root cause → resolution)."""

    __tablename__ = "operational_experiences"

    problem: Mapped[str] = mapped_column(String(500), index=True)
    symptoms: Mapped[list[Any]] = mapped_column(PortableJSON, default=list)
    root_cause: Mapped[str | None] = mapped_column(Text())
    resolution: Mapped[str | None] = mapped_column(Text())
    lessons_learned: Mapped[str | None] = mapped_column(Text())
    confidence: Mapped[float] = mapped_column(Float(), default=0.5)
    source: Mapped[ExperienceSource] = mapped_column(
        portable_enum(ExperienceSource), default=ExperienceSource.USER_TEACHING, index=True
    )
    author: Mapped[str | None] = mapped_column(String(200))
    related_technologies: Mapped[list[Any]] = mapped_column(PortableJSON, default=list)

    incident_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("incidents.id"))
    incident: Mapped["Incident | None"] = relationship(back_populates="experiences")

    def __repr__(self) -> str:
        return f"<OperationalExperience {self.problem!r} confidence={self.confidence}>"
