"""Repository entity: a source code repository."""

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from opsmemory.db.base import Base, PortableJSON, PrimaryKeyMixin, TimestampMixin
from opsmemory.db.types import GUID

if TYPE_CHECKING:
    from opsmemory.db.models.document import Document
    from opsmemory.db.models.service import Service
    from opsmemory.db.models.team import Team


class Repository(Base, PrimaryKeyMixin, TimestampMixin):
    """A source code repository (e.g. payments-api, terraform-platform)."""

    __tablename__ = "repositories"

    name: Mapped[str] = mapped_column(String(300), index=True)
    provider: Mapped[str | None] = mapped_column(String(50))
    url: Mapped[str | None] = mapped_column(String(2000), unique=True)
    default_branch: Mapped[str | None] = mapped_column(String(200))
    language: Mapped[str | None] = mapped_column(String(100))
    visibility: Mapped[str | None] = mapped_column(String(20))
    topics: Mapped[list[Any]] = mapped_column(PortableJSON, default=list)

    owner_team_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("teams.id"))
    owner_team: Mapped["Team | None"] = relationship(back_populates="repositories")

    documents: Mapped[list["Document"]] = relationship(back_populates="repository")
    services: Mapped[list["Service"]] = relationship(back_populates="repository")

    def __repr__(self) -> str:
        return f"<Repository {self.name!r}>"
