"""Memory engine factory."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from opsmemory.ai.base import EmbeddingProvider
from opsmemory.core.config import Settings
from opsmemory.core.errors import OpsMemoryError
from opsmemory.core.logging import get_logger
from opsmemory.memory.base import MemoryEngine
from opsmemory.memory.native import NativeMemoryEngine

logger = get_logger(__name__)


def build_memory_engine(
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    embeddings: EmbeddingProvider,
) -> MemoryEngine:
    """Build the configured memory engine.

    ``cognee`` (default) is the central engine: it composes the native
    pgvector substrate and cognifies every write into a knowledge graph.
    ``native`` exposes the raw substrate (used by tests). An unexpected
    failure constructing Cognee falls back to the substrate loudly rather
    than taking the platform down.
    """
    native = NativeMemoryEngine(session_factory, embeddings)
    if settings.memory_engine == "native":
        return native
    if settings.memory_engine == "cognee":
        from opsmemory.memory.cognee_engine import CogneeMemoryEngine

        try:
            return CogneeMemoryEngine(native, settings)
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Failed to build Cognee engine (%s); falling back to substrate", exc)
            return native
    raise OpsMemoryError(
        f"Unknown memory engine: {settings.memory_engine!r} (expected 'cognee' or 'native')",
        code="CONFIGURATION_ERROR",
        status_code=500,
    )
