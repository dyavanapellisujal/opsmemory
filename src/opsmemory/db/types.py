"""Cross-dialect column types.

Migrations target PostgreSQL, but unit tests run against SQLite for speed,
so column types that differ per dialect are wrapped here.
"""

import uuid
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import CHAR, JSON, Dialect
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.types import TypeDecorator, TypeEngine

EMBEDDING_DIM = 768
"""Fixed pgvector column dimension; OPSMEMORY_EMBEDDING_DIMENSION must match."""


class GUID(TypeDecorator[uuid.UUID]):
    """Platform-independent UUID column.

    Uses PostgreSQL's native ``UUID`` type when available and falls back to
    ``CHAR(36)`` on other dialects (e.g. SQLite in tests).
    """

    impl = CHAR(36)
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[Any]:
        """Select the concrete type for the active dialect."""
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value: uuid.UUID | str | None, dialect: Dialect) -> Any:
        """Serialize a UUID for storage."""
        if value is None:
            return value
        if dialect.name == "postgresql":
            return value
        return str(value)

    def process_result_value(self, value: Any, dialect: Dialect) -> uuid.UUID | None:
        """Deserialize a stored value back into a ``uuid.UUID``."""
        if value is None:
            return None
        if isinstance(value, uuid.UUID):
            return value
        return uuid.UUID(str(value))


class PortableVector(TypeDecorator[list[float]]):
    """Embedding column: native pgvector on PostgreSQL, JSON elsewhere.

    SQLite (tests) stores the raw float list as JSON; similarity search
    falls back to in-Python cosine in the native memory engine.
    """

    impl = JSON
    cache_ok = True

    def __init__(self, dimension: int = EMBEDDING_DIM) -> None:
        super().__init__()
        self.dimension = dimension

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[Any]:
        """Select pgvector's Vector type on PostgreSQL, JSON otherwise."""
        if dialect.name == "postgresql":
            return dialect.type_descriptor(Vector(self.dimension))
        return dialect.type_descriptor(JSON())

    def process_result_value(self, value: Any, dialect: Dialect) -> list[float] | None:
        """Always return a plain list of floats (pgvector yields numpy arrays)."""
        if value is None:
            return None
        return [float(v) for v in value]
