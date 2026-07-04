"""Cognee memory engine: central engine that degrades to the substrate keyless.

These run without an LLM key, so cognification is inactive and the engine
transparently uses the pgvector substrate — proving Cognee is always in the
path and the platform stays functional with no model to call.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from opsmemory.core.config import Environment, Settings
from opsmemory.domain.enums import MemoryKind
from opsmemory.memory.base import MemoryItem
from opsmemory.memory.cognee_engine import CogneeMemoryEngine
from opsmemory.memory.factory import build_memory_engine
from opsmemory.memory.native import NativeMemoryEngine


def _settings(**over: object) -> Settings:
    return Settings(
        _env_file=None,
        environment=Environment.TEST,
        embedding_provider="hashing",
        llm_provider="none",
        embedding_dimension=64,
        **over,  # type: ignore[arg-type]
    )


def test_factory_defaults_to_cognee() -> None:
    assert _settings().memory_engine == "cognee"


async def test_cognee_engine_degrades_to_substrate_without_keys(
    memory_engine: NativeMemoryEngine,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    engine = CogneeMemoryEngine(memory_engine, _settings())
    assert engine.name == "cognee"
    # No Gemini key → cognification is inactive; writes still persist + retrieve.
    assert engine._cognify_enabled is False

    ids = await engine.add(
        [MemoryItem(kind=MemoryKind.CHUNK, content="Redis auth failed; rotate the secret.")]
    )
    assert len(ids) == 1
    results = await engine.search("redis authentication", limit=3)
    assert results and "edis" in results[0].content
    assert await engine.recall("anything") is None


async def test_cognee_engine_delete_delegates(
    memory_engine: NativeMemoryEngine,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    engine = CogneeMemoryEngine(memory_engine, _settings())
    doc_id = uuid.uuid4()
    await engine.add([MemoryItem(kind=MemoryKind.CHUNK, content="doc chunk", document_id=doc_id)])
    assert await engine.delete_for_document(doc_id) == 1


def test_factory_builds_cognee_engine(
    memory_engine: NativeMemoryEngine,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    from opsmemory.ai.providers import HashingEmbeddingProvider

    engine = build_memory_engine(
        _settings(memory_engine="cognee"), session_factory, HashingEmbeddingProvider(dimension=64)
    )
    assert engine.name == "cognee"
