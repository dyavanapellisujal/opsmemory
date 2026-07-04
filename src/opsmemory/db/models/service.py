"""Service entity: an application, infrastructure component, or platform service."""

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import Column, ForeignKey, String, Table, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from opsmemory.db.base import Base, PortableJSON, PrimaryKeyMixin, TimestampMixin
from opsmemory.db.types import GUID

if TYPE_CHECKING:
    from opsmemory.db.models.repository import Repository
    from opsmemory.db.models.team import Team

# Self-referential many-to-many: Service → depends on → Service.
service_dependencies = Table(
    "service_dependencies",
    Base.metadata,
    Column("service_id", GUID(), ForeignKey("services.id"), primary_key=True),
    Column("depends_on_id", GUID(), ForeignKey("services.id"), primary_key=True),
)


class Service(Base, PrimaryKeyMixin, TimestampMixin):
    """A deployable application or platform component (e.g. payments-api, redis)."""

    __tablename__ = "services"

    name: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text())
    environment: Mapped[str | None] = mapped_column(String(50))
    namespace: Mapped[str | None] = mapped_column(String(200))
    runtime: Mapped[str | None] = mapped_column(String(100))
    sla: Mapped[str | None] = mapped_column(String(100))
    technology_stack: Mapped[list[Any]] = mapped_column(PortableJSON, default=list)

    owner_team_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("teams.id"))
    owner_team: Mapped["Team | None"] = relationship(back_populates="services")

    repository_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("repositories.id"))
    repository: Mapped["Repository | None"] = relationship(back_populates="services")

    dependencies: Mapped[list["Service"]] = relationship(
        secondary=service_dependencies,
        primaryjoin=lambda: Service.id == service_dependencies.c.service_id,
        secondaryjoin=lambda: Service.id == service_dependencies.c.depends_on_id,
        backref="dependents",
    )

    def __repr__(self) -> str:
        return f"<Service {self.name!r}>"
