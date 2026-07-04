"""Connector and ingestion job entities."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from opsmemory.db.base import Base, PortableJSON, PrimaryKeyMixin, TimestampMixin, portable_enum
from opsmemory.db.types import GUID
from opsmemory.domain.enums import ConnectorStatus, ConnectorType, JobStatus

if TYPE_CHECKING:
    from opsmemory.db.models.document import Document


class Connector(Base, PrimaryKeyMixin, TimestampMixin):
    """A configured external knowledge source (GitHub, local files, HTTP docs)."""

    __tablename__ = "connectors"

    name: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    type: Mapped[ConnectorType] = mapped_column(portable_enum(ConnectorType), index=True)
    config: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)
    status: Mapped[ConnectorStatus] = mapped_column(
        portable_enum(ConnectorStatus), default=ConnectorStatus.ACTIVE
    )
    enabled: Mapped[bool] = mapped_column(Boolean(), default=True)
    checkpoint: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)
    last_sync_at: Mapped[datetime | None] = mapped_column()

    documents: Mapped[list["Document"]] = relationship(back_populates="connector")
    jobs: Mapped[list["IngestionJob"]] = relationship(back_populates="connector")

    def __repr__(self) -> str:
        return f"<Connector {self.name!r} type={self.type}>"


class IngestionJob(Base, PrimaryKeyMixin, TimestampMixin):
    """A long-running ingestion run triggered for a connector."""

    __tablename__ = "ingestion_jobs"

    status: Mapped[JobStatus] = mapped_column(
        portable_enum(JobStatus), default=JobStatus.PENDING, index=True
    )
    stats: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text())
    started_at: Mapped[datetime | None] = mapped_column()
    finished_at: Mapped[datetime | None] = mapped_column()

    connector_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("connectors.id"))
    connector: Mapped[Connector] = relationship(back_populates="jobs")

    def __repr__(self) -> str:
        return f"<IngestionJob {self.id} status={self.status}>"
