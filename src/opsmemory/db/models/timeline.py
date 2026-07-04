"""Incident timeline events and user notifications.

Timeline events are the operational history of an incident (meeting joined,
transcript processed, experience learned, documentation updated). Every
completed meeting appends events, giving the incident a live timeline.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from opsmemory.db.base import Base, PortableJSON, PrimaryKeyMixin, TimestampMixin
from opsmemory.db.types import GUID

if TYPE_CHECKING:
    from opsmemory.db.models.incident import Incident


class IncidentEvent(Base, PrimaryKeyMixin, TimestampMixin):
    """A single event on an incident's timeline."""

    __tablename__ = "incident_events"

    incident_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("incidents.id", ondelete="CASCADE"), index=True
    )
    at: Mapped[datetime] = mapped_column(index=True)
    kind: Mapped[str] = mapped_column(String(60), index=True)
    label: Mapped[str] = mapped_column(Text())
    meeting_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("meetings.id", ondelete="CASCADE")
    )
    meta: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)

    incident: Mapped["Incident"] = relationship()

    def __repr__(self) -> str:
        return f"<IncidentEvent {self.kind} @ {self.at}>"


class Notification(Base, PrimaryKeyMixin, TimestampMixin):
    """A user-facing lifecycle notification (polled by the web app)."""

    __tablename__ = "notifications"

    kind: Mapped[str] = mapped_column(String(60), index=True)
    title: Mapped[str] = mapped_column(String(300))
    body: Mapped[str | None] = mapped_column(Text())
    incident_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("incidents.id", ondelete="CASCADE")
    )
    read: Mapped[bool] = mapped_column(default=False, index=True)

    def __repr__(self) -> str:
        return f"<Notification {self.kind}: {self.title!r}>"
