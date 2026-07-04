"""Hybrid retrieval engine (PRD Milestone: Hybrid Retrieval).

Combines semantic (pgvector), keyword, metadata, and graph strategies based
on the classified intent, ranks candidates, and assembles a bounded context
package for the AI agent. Strategy selection is deterministic and
cost-aware: graph-only questions never touch embeddings, and vice versa.
"""

import re
import uuid
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from opsmemory.core.config import Settings
from opsmemory.db.models import Document, OperationalExperience, Service, Team
from opsmemory.domain.enums import MemoryKind
from opsmemory.graph.store import GraphEdge, GraphStore
from opsmemory.memory.base import MemoryEngine, ScoredMemory
from opsmemory.retrieval.classifier import Intent, classify


class DocumentEvidence(BaseModel):
    """A supporting document reference."""

    id: uuid.UUID
    title: str
    source: str
    url: str | None = None
    snippet: str


class ExperienceEvidence(BaseModel):
    """A supporting operational experience."""

    id: uuid.UUID
    problem: str
    root_cause: str | None = None
    resolution: str | None = None
    lessons_learned: str | None = None
    confidence: float


class ServiceFact(BaseModel):
    """Structured metadata about a service relevant to the query."""

    name: str
    description: str | None = None
    owner_team: str | None = None
    environment: str | None = None


class ContextPackage(BaseModel):
    """Curated evidence handed to the AI agent (never raw repositories)."""

    query: str
    intent: Intent
    memories: list[ScoredMemory] = Field(default_factory=list)
    documents: list[DocumentEvidence] = Field(default_factory=list)
    experiences: list[ExperienceEvidence] = Field(default_factory=list)
    services: list[ServiceFact] = Field(default_factory=list)
    graph_facts: list[GraphEdge] = Field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        """True when no evidence of any type was found."""
        return not (
            self.memories or self.documents or self.experiences or self.services or self.graph_facts
        )


class RetrievalEngine:
    """Selects strategies, executes them, ranks results, assembles context."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        memory_engine: MemoryEngine,
        graph: GraphStore,
        settings: Settings,
    ) -> None:
        self._session_factory = session_factory
        self._memory = memory_engine
        self._graph = graph
        self._settings = settings

    async def retrieve(self, query: str) -> ContextPackage:
        """Run intent-appropriate strategies and assemble the context package."""
        intent = classify(query)
        package = ContextPackage(query=query, intent=intent)

        async with self._session_factory() as session:
            mentioned = await self._mentioned_services(session, query)
            package.services = [
                ServiceFact(
                    name=s.name,
                    description=s.description,
                    owner_team=s.owner_team.name if s.owner_team else None,
                    environment=s.environment,
                )
                for s in mentioned
            ]

            if intent in (Intent.DEPENDENCY, Intent.OWNERSHIP):
                for service in mentioned:
                    hops = self._settings.retrieval_max_graph_hops
                    if intent is Intent.DEPENDENCY:
                        package.graph_facts.extend(
                            await self._graph.dependencies(service.name, depth=hops)
                        )
                    else:
                        package.graph_facts.extend(
                            await self._graph.neighbors(service.name, depth=1)
                        )
                # Ownership/dependency answers are structural; skip semantic
                # search entirely when structure already answered the query.
                if package.graph_facts or package.services:
                    package.documents = await self._keyword_documents(session, query, limit=2)
                    return package

            kinds = [MemoryKind.EXPERIENCE] if intent is Intent.HISTORICAL else None
            package.memories = await self._memory.search(
                query, limit=self._settings.retrieval_max_memories, kinds=kinds
            )
            package.experiences = await self._experiences_for(session, package.memories, query)
            package.documents = await self._keyword_documents(
                session, query, limit=self._settings.retrieval_max_documents
            )
            if mentioned:
                for service in mentioned[:2]:
                    package.graph_facts.extend(await self._graph.neighbors(service.name, depth=1))
        return package

    async def _mentioned_services(self, session: AsyncSession, query: str) -> list[Service]:
        """Metadata strategy: services whose names appear in the query."""
        from sqlalchemy.orm import selectinload

        services = (
            (await session.execute(select(Service).options(selectinload(Service.owner_team))))
            .scalars()
            .all()
        )
        lowered = query.lower()
        return [s for s in services if re.search(rf"\b{re.escape(s.name.lower())}\b", lowered)]

    async def _keyword_documents(
        self, session: AsyncSession, query: str, *, limit: int
    ) -> list[DocumentEvidence]:
        """Keyword strategy: title/content ILIKE over meaningful query terms."""
        terms = [t for t in re.findall(r"[a-zA-Z0-9._-]{3,}", query) if not _is_stopword(t)]
        if not terms:
            return []
        conditions = [Document.title.ilike(f"%{t}%") for t in terms[:6]]
        conditions += [Document.content.ilike(f"%{t}%") for t in terms[:6]]
        rows = (
            (await session.execute(select(Document).where(or_(*conditions)).limit(limit * 3)))
            .scalars()
            .all()
        )
        ranked = sorted(
            rows,
            key=lambda d: sum(t.lower() in (d.title or "").lower() for t in terms),
            reverse=True,
        )
        return [
            DocumentEvidence(
                id=d.id,
                title=d.title,
                source=d.source.value,
                url=d.url,
                snippet=_snippet(d.content, terms),
            )
            for d in ranked[:limit]
        ]

    async def _experiences_for(
        self, session: AsyncSession, memories: list[ScoredMemory], query: str
    ) -> list[ExperienceEvidence]:
        """Load experiences referenced by retrieved memories, plus keyword hits."""
        ids = {m.experience_id for m in memories if m.experience_id is not None}
        stmt = select(OperationalExperience)
        terms = [t for t in re.findall(r"[a-zA-Z0-9._-]{3,}", query) if not _is_stopword(t)]
        conditions: list[Any] = []
        if ids:
            conditions.append(OperationalExperience.id.in_(ids))
        for term in terms[:6]:
            conditions.append(OperationalExperience.problem.ilike(f"%{term}%"))
        if not conditions:
            return []
        rows = (
            (
                await session.execute(
                    stmt.where(or_(*conditions))
                    .order_by(OperationalExperience.confidence.desc())
                    .limit(self._settings.retrieval_max_experiences)
                )
            )
            .scalars()
            .all()
        )
        return [
            ExperienceEvidence(
                id=e.id,
                problem=e.problem,
                root_cause=e.root_cause,
                resolution=e.resolution,
                lessons_learned=e.lessons_learned,
                confidence=e.confidence,
            )
            for e in rows
        ]


async def team_owner_lookup(session: AsyncSession, name: str) -> Team | None:
    """Convenience metadata lookup used by ownership answers."""
    return (await session.execute(select(Team).where(Team.name.ilike(name)))).scalar_one_or_none()


_STOPWORDS = {
    "the", "and", "for", "how", "why", "who", "what", "which", "does", "did", "has",
    "have", "was", "were", "are", "can", "could", "should", "would", "with", "this",
    "that", "from", "into", "our", "you", "use", "using", "about", "before", "after",
}  # fmt: skip


def _is_stopword(term: str) -> bool:
    """True for common English words that add noise to keyword search."""
    return term.lower() in _STOPWORDS


def _snippet(content: str, terms: list[str], *, width: int = 240) -> str:
    """Extract a short window around the first matching term."""
    lowered = content.lower()
    for term in terms:
        index = lowered.find(term.lower())
        if index >= 0:
            start = max(0, index - width // 3)
            return content[start : start + width].strip()
    return content[:width].strip()
