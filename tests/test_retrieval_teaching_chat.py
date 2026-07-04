"""Tests for intent classification, retrieval, teaching, and the chat agent."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from opsmemory.agent.chat import ChatService
from opsmemory.core.config import Settings
from opsmemory.db.models import Service, Team
from opsmemory.domain.enums import MemoryKind
from opsmemory.graph.kuzu_store import KuzuGraphStore
from opsmemory.graph.store import GraphEdge
from opsmemory.memory.base import MemoryItem
from opsmemory.memory.native import NativeMemoryEngine
from opsmemory.retrieval.classifier import Intent, classify
from opsmemory.retrieval.engine import RetrievalEngine
from opsmemory.teaching.service import TeachingService


class FakeLLM:
    """LLM stub returning a canned completion."""

    name = "fake"
    model = "fake-1"

    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list[tuple[str, str]] = []

    async def complete(self, system: str, user: str, *, max_tokens: int) -> str:
        self.calls.append((system, user))
        return self.response


def test_intent_classification() -> None:
    assert classify("Remember this: we fixed it by rotating the secret") is Intent.TEACHING
    assert classify("Who owns the kafka cluster?") is Intent.OWNERSHIP
    assert classify("Which services depend on redis?") is Intent.DEPENDENCY
    assert classify("Have we seen this error before?") is Intent.HISTORICAL
    assert classify("How do we deploy payments-api?") is Intent.KNOWLEDGE


async def test_retrieval_dependency_uses_graph_not_semantic(
    session_factory: async_sessionmaker[AsyncSession],
    memory_engine: NativeMemoryEngine,
    graph_store: KuzuGraphStore,
    settings: Settings,
) -> None:
    async with session_factory() as session:
        team = Team(name="platform")
        session.add_all([team, Service(name="payments-api", owner_team=team)])
        await session.commit()
    await graph_store.upsert_edge(
        GraphEdge(source="payments-api", relation="depends_on", target="redis")
    )

    engine = RetrievalEngine(session_factory, memory_engine, graph_store, settings)
    package = await engine.retrieve("Which services does payments-api depend on?")
    assert package.intent is Intent.DEPENDENCY
    assert {(e.source, e.target) for e in package.graph_facts} == {("payments-api", "redis")}
    assert package.memories == []  # cost-aware: no semantic search for graph questions
    assert package.services[0].owner_team == "platform"


async def test_retrieval_knowledge_combines_semantic_and_keyword(
    session_factory: async_sessionmaker[AsyncSession],
    memory_engine: NativeMemoryEngine,
    graph_store: KuzuGraphStore,
    settings: Settings,
) -> None:
    await memory_engine.add(
        [MemoryItem(kind=MemoryKind.CHUNK, content="Rotate the redis secret and restart")]
    )
    engine = RetrievalEngine(session_factory, memory_engine, graph_store, settings)
    package = await engine.retrieve("How do we recover redis?")
    assert package.intent is Intent.KNOWLEDGE
    assert package.memories and "redis" in package.memories[0].content


async def test_teaching_heuristic_extraction_without_llm(
    session_factory: async_sessionmaker[AsyncSession],
    memory_engine: NativeMemoryEngine,
    graph_store: KuzuGraphStore,
) -> None:
    teaching = TeachingService(session_factory, memory_engine, graph_store, llm=None)
    result = await teaching.teach(
        "The redis outage happened because the credentials expired. "
        "We fixed it by rotating the kubernetes secret. "
        "Lesson learned: rotate credentials before expiry.",
        author="alice",
    )
    assert result.created
    assert result.root_cause is not None and "credentials expired" in result.root_cause
    assert result.resolution is not None and "rotating" in result.resolution
    assert result.confidence == 0.6


async def test_teaching_llm_extraction_and_duplicate_reinforcement(
    session_factory: async_sessionmaker[AsyncSession],
    memory_engine: NativeMemoryEngine,
    graph_store: KuzuGraphStore,
) -> None:
    llm = FakeLLM(
        '{"problem": "Redis auth failure", "root_cause": "Expired credentials", '
        '"resolution": "Rotate secret", "lessons_learned": "Rotate early", "symptoms": []}'
    )
    teaching = TeachingService(session_factory, memory_engine, graph_store, llm=llm)
    first = await teaching.teach("Redis broke, we rotated the secret. Remember this.")
    assert first.created and first.problem == "Redis auth failure"

    # The same lesson taught again reinforces instead of duplicating.
    second = await teaching.teach("Redis broke, we rotated the secret. Remember this.")
    assert not second.created
    assert second.duplicate_of == first.experience_id
    assert second.confidence > first.confidence


async def test_chat_routes_teaching_and_answers_with_citations(
    session_factory: async_sessionmaker[AsyncSession],
    memory_engine: NativeMemoryEngine,
    graph_store: KuzuGraphStore,
    settings: Settings,
) -> None:
    llm = FakeLLM("Rotate the redis secret, as done in incident 42.")
    retrieval = RetrievalEngine(session_factory, memory_engine, graph_store, settings)
    teaching = TeachingService(session_factory, memory_engine, graph_store, llm=None)
    chat = ChatService(retrieval, teaching, llm)

    taught = await chat.chat("We solved this by rotating the redis secret. Remember this.")
    assert taught.taught and taught.intent is Intent.TEACHING

    answered = await chat.chat("How do we fix redis auth failures?")
    assert "rotate" in answered.answer.lower()
    assert answered.citations, "expected evidence citations"
    assert 0 < answered.confidence <= 0.95
    # The LLM must have received curated evidence, not raw documents.
    assert "OPERATIONAL EXPERIENCES" in llm.calls[0][1] or "SEMANTIC MEMORIES" in llm.calls[0][1]


async def test_chat_empty_knowledge_communicates_uncertainty(
    session_factory: async_sessionmaker[AsyncSession],
    memory_engine: NativeMemoryEngine,
    graph_store: KuzuGraphStore,
    settings: Settings,
) -> None:
    retrieval = RetrievalEngine(session_factory, memory_engine, graph_store, settings)
    teaching = TeachingService(session_factory, memory_engine, graph_store, llm=None)
    chat = ChatService(retrieval, teaching, llm=None)
    response = await chat.chat("What is the melting point of unobtainium?")
    assert response.confidence == 0.0
    assert "don't have" in response.answer
