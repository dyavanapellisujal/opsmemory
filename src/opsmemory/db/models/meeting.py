"""Meeting entities: recorded meetings, their transcripts, and summaries.

The raw transcript is retained in PostgreSQL for traceability (source of
truth, ADR-0003); only structured knowledge extracted from it flows into
the memory engine and graph.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from opsmemory.db.base import Base, PortableJSON, PrimaryKeyMixin, TimestampMixin, portable_enum
from opsmemory.db.types import GUID
from opsmemory.domain.enums import MeetingProvider, MeetingStatus

if TYPE_CHECKING:
    from opsmemory.db.models.incident import Incident


class Meeting(Base, PrimaryKeyMixin, TimestampMixin):
    """A meeting recorded by the OpsMemory bot via Recall.ai."""

    __tablename__ = "meetings"

    recall_bot_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    meeting_url: Mapped[str] = mapped_column(String(2000))
    provider: Mapped[MeetingProvider] = mapped_column(
        portable_enum(MeetingProvider), default=MeetingProvider.UNKNOWN
    )
    title: Mapped[str | None] = mapped_column(String(500))
    organizer: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[MeetingStatus] = mapped_column(
        portable_enum(MeetingStatus), default=MeetingStatus.SCHEDULED, index=True
    )
    recording_url: Mapped[str | None] = mapped_column(String(2000))
    transcript_url: Mapped[str | None] = mapped_column(String(2000))
    transcript_downloaded: Mapped[bool] = mapped_column(Boolean(), default=False)
    summary_generated: Mapped[bool] = mapped_column(Boolean(), default=False)
    cognee_synced: Mapped[bool] = mapped_column(Boolean(), default=False)
    error: Mapped[str | None] = mapped_column(Text())
    duration_seconds: Mapped[int | None] = mapped_column(Integer())
    participants: Mapped[list[Any]] = mapped_column(PortableJSON, default=list)
    started_at: Mapped[datetime | None] = mapped_column()
    ended_at: Mapped[datetime | None] = mapped_column()

    incident_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("incidents.id", ondelete="SET NULL"), index=True
    )
    incident: Mapped["Incident | None"] = relationship(back_populates="meetings")

    transcript: Mapped["MeetingTranscript | None"] = relationship(
        back_populates="meeting", uselist=False
    )
    summary: Mapped["MeetingSummary | None"] = relationship(back_populates="meeting", uselist=False)

    def __repr__(self) -> str:
        return f"<Meeting {self.title!r} status={self.status}>"


class MeetingTranscript(Base, PrimaryKeyMixin, TimestampMixin):
    """The full speaker-attributed transcript of a meeting."""

    __tablename__ = "meeting_transcripts"

    meeting_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("meetings.id", ondelete="CASCADE"), unique=True, index=True
    )
    transcript: Mapped[str] = mapped_column(Text())
    token_count: Mapped[int] = mapped_column(Integer(), default=0)

    meeting: Mapped[Meeting] = relationship(back_populates="transcript")

    def __repr__(self) -> str:
        return f"<MeetingTranscript meeting={self.meeting_id} tokens={self.token_count}>"


class MeetingSummary(Base, PrimaryKeyMixin, TimestampMixin):
    """Structured incident knowledge extracted from a meeting transcript."""

    __tablename__ = "meeting_summaries"

    meeting_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("meetings.id", ondelete="CASCADE"), unique=True, index=True
    )
    summary: Mapped[str] = mapped_column(Text())
    structured_json: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)

    meeting: Mapped[Meeting] = relationship(back_populates="summary")

    def __repr__(self) -> str:
        return f"<MeetingSummary meeting={self.meeting_id}>"
