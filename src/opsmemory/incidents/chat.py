"""Incident-scoped and incident-aware chat.

Scoped chat answers questions using ONLY a single incident's memories and
documentation. The global helper maps retrieved memories back to incidents
so the global assistant can cite related incidents.
"""

import uuid
from collections import defaultdict

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from opsmemory.ai.base import LLMProvider
from opsmemory.core.logging import get_logger
from opsmemory.db.models import Incident, OperationalExperience
from opsmemory.memory.base import MemoryEngine

logger = get_logger(__name__)

_SCOPED_SYSTEM_PROMPT = """You are OpsMemory, answering about ONE specific engineering incident.
Use ONLY the evidence provided below — it all belongs to this incident. Never invent facts.
If the evidence does not answer the question, say so and suggest what to add to this incident.
Be concise and practical; ground every statement in the evidence."""


class RelatedIncident(BaseModel):
    """An incident surfaced as relevant to a query."""

    incident_id: uuid.UUID
    reference: str
    title: str
    score: float


class ScopedAnswer(BaseModel):
    """An incident-scoped chat answer."""

    answer: str
    confidence: float = Field(ge=0.0, le=1.0)
    citations: list[str] = Field(default_factory=list)


class IncidentChatService:
    """Answers questions scoped to a single incident, plus global mapping."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        memory_engine: MemoryEngine,
        llm: LLMProvider | None,
        llm_max_tokens: int = 1500,
    ) -> None:
        self._session_factory = session_factory
        self._memory = memory_engine
        self._llm = llm
        self._llm_max_tokens = llm_max_tokens

    async def chat(self, incident_id: uuid.UUID, message: str) -> ScopedAnswer:
        """Answer a question using only this incident's knowledge."""
        matches = await self._memory.search(message, limit=25)
        scoped = [m for m in matches if m.incident_id == incident_id][:8]

        async with self._session_factory() as session:
            incident = (
                await session.execute(select(Incident).where(Incident.id == incident_id))
            ).scalar_one_or_none()
            experiences = (
                (
                    await session.execute(
                        select(OperationalExperience).where(
                            OperationalExperience.incident_id == incident_id
                        )
                    )
                )
                .scalars()
                .all()
            )

        if incident is None:
            return ScopedAnswer(answer="Incident not found.", confidence=0.0)

        context_lines = [f"INCIDENT {incident.reference}: {incident.title}", ""]
        citations: list[str] = []
        if incident.root_cause:
            context_lines.append(f"Root cause: {incident.root_cause}")
        if incident.resolution:
            context_lines.append(f"Resolution: {incident.resolution}")
        for exp in experiences:
            context_lines.append(
                f"Experience: {exp.problem} — resolution: {exp.resolution or 'n/a'}"
            )
            citations.append(f"experience:{exp.problem[:50]}")
        for memory in scoped:
            section = f" [{memory.section}]" if memory.section else ""
            context_lines.append(f"(score {memory.score:.2f}){section} {memory.content[:500]}")
            if memory.section:
                citations.append(memory.section)

        has_evidence = bool(scoped or experiences or incident.root_cause or incident.resolution)
        if not has_evidence:
            return ScopedAnswer(
                answer=(
                    "This incident has no ingested knowledge yet. Upload a document, "
                    "attach a meeting, or add a manual entry on the Data Collection tab."
                ),
                confidence=0.0,
            )
        confidence = round(min(0.9, 0.3 + 0.5 * (max((m.score for m in scoped), default=0.0))), 2)

        if self._llm is None:
            summary = "\n".join(context_lines[2:8])
            return ScopedAnswer(
                answer=f"(No LLM configured — evidence summary)\n{summary}",
                confidence=round(confidence * 0.8, 2),
                citations=citations[:8],
            )
        try:
            answer = await self._llm.complete(
                _SCOPED_SYSTEM_PROMPT,
                f"QUESTION: {message}\n\nEVIDENCE:\n" + "\n".join(context_lines),
                max_tokens=self._llm_max_tokens,
            )
        except Exception as exc:
            logger.warning("Scoped chat LLM failed incident_id=%s: %s", incident_id, exc)
            return ScopedAnswer(
                answer="\n".join(context_lines[2:8]),
                confidence=round(confidence * 0.6, 2),
                citations=citations[:8],
            )
        return ScopedAnswer(answer=answer.strip(), confidence=confidence, citations=citations[:8])

    async def related_incidents(self, query: str, *, limit: int = 5) -> list[RelatedIncident]:
        """Map memories matching a query back to their incidents (global chat)."""
        matches = await self._memory.search(query, limit=30)
        best: dict[uuid.UUID, float] = defaultdict(float)
        for match in matches:
            if match.incident_id is not None:
                best[match.incident_id] = max(best[match.incident_id], match.score)
        if not best:
            return []
        async with self._session_factory() as session:
            incidents = {
                inc.id: inc
                for inc in (
                    await session.execute(select(Incident).where(Incident.id.in_(list(best))))
                )
                .scalars()
                .all()
            }
        related = [
            RelatedIncident(
                incident_id=iid,
                reference=incidents[iid].reference,
                title=incidents[iid].title,
                score=round(score, 3),
            )
            for iid, score in best.items()
            if iid in incidents
        ]
        related.sort(key=lambda r: r.score, reverse=True)
        return related[:limit]
