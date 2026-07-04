"""Team entity: an engineering team that owns services and repositories."""

from typing import TYPE_CHECKING, Any

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from opsmemory.db.base import Base, PortableJSON, PrimaryKeyMixin, TimestampMixin

if TYPE_CHECKING:
    from opsmemory.db.models.repository import Repository
    from opsmemory.db.models.service import Service


class Team(Base, PrimaryKeyMixin, TimestampMixin):
    """An engineering team (e.g. Platform Engineering, Payments)."""

    __tablename__ = "teams"

    name: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text())
    slack_channel: Mapped[str | None] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(320))
    responsibilities: Mapped[list[Any]] = mapped_column(PortableJSON, default=list)

    services: Mapped[list["Service"]] = relationship(back_populates="owner_team")
    repositories: Mapped[list["Repository"]] = relationship(back_populates="owner_team")

    def __repr__(self) -> str:
        return f"<Team {self.name!r}>"
