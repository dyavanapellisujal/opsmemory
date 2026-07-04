"""Declarative base and shared model mixins."""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import JSON, Enum, MetaData, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from opsmemory.db.types import GUID

# Deterministic constraint naming so Alembic migrations stay stable.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# JSON that upgrades to JSONB on PostgreSQL.
PortableJSON = JSON().with_variant(JSONB(), "postgresql")


def portable_enum(enum_cls: type[StrEnum], length: int = 30) -> Enum:
    """Build a cross-dialect enum column type stored as its string values.

    Native database enums are avoided so adding enum members never requires
    an ``ALTER TYPE`` migration and the schema stays portable across dialects.

    Args:
        enum_cls: The :class:`~enum.StrEnum` to store.
        length: Maximum stored string length.
    """
    return Enum(
        enum_cls,
        native_enum=False,
        length=length,
        values_callable=lambda e: [m.value for m in e],
    )


class Base(DeclarativeBase):
    """Declarative base for all OpsMemory ORM models."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class PrimaryKeyMixin:
    """UUID primary key shared by all entities."""

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    """Creation / modification timestamps maintained by the database."""

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
