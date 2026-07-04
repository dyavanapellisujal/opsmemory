"""Teaching pipeline (PRD Continuous Learning).

New knowledge flows through: extraction → duplicate detection → confidence
assessment → memory construction → graph update. Extraction uses the LLM
when configured and falls back to deterministic heuristics otherwise, so
teaching always works.
"""

import json
import re
import uuid

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from opsmemory.ai.base import LLMProvider
from opsmemory.core.logging import get_logger
from opsmemory.db.models import OperationalExperience
from opsmemory.domain.enums import ExperienceSource, MemoryKind
from opsmemory.graph.store import GraphEdge, GraphStore
from opsmemory.memory.base import MemoryEngine, MemoryItem
from opsmemory.processing.relationships import extract_technologies

logger = get_logger(__name__)

_DUPLICATE_THRESHOLD = 0.90
_EXTRACTION_PROMPT = """You extract structured operational experiences from engineering text.
Respond with ONLY a JSON object with these string fields (use null when absent):
problem, root_cause, resolution, lessons_learned, and symptoms (array of strings).
Keep each field concise (one or two sentences)."""


class TeachingResult(BaseModel):
    """Outcome of a teaching interaction."""

    experience_id: uuid.UUID
    created: bool
    problem: str
    root_cause: str | None = None
    resolution: str | None = None
    lessons_learned: str | None = None
    confidence: float
    duplicate_of: uuid.UUID | None = None
    message: str


class ExtractedExperience(BaseModel):
    """Structured fields extracted from contributed text."""

    problem: str
    symptoms: list[str] = []
    root_cause: str | None = None
    resolution: str | None = None
    lessons_learned: str | None = None


class TeachingService:
    """Validates, structures, deduplicates, and stores contributed knowledge."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        memory_engine: MemoryEngine,
        graph: GraphStore,
        llm: LLMProvider | None,
        llm_max_tokens: int = 1024,
    ) -> None:
        self._session_factory = session_factory
        self._memory = memory_engine
        self._graph = graph
        self._llm = llm
        self._llm_max_tokens = llm_max_tokens

    async def teach(
        self,
        content: str,
        *,
        author: str | None = None,
        source: ExperienceSource = ExperienceSource.USER_TEACHING,
        extracted: ExtractedExperience | None = None,
        incident_id: uuid.UUID | None = None,
    ) -> TeachingResult:
        """Process a contributed operational lesson end to end.

        Args:
            content: Free-text description of the problem and how it was solved.
            author: Optional contributor identifier.
            source: How the knowledge entered the platform (user vs extraction).
            extracted: Pre-structured experience (e.g. from the meeting
                pipeline's dedicated extraction) — skips re-extraction.
            incident_id: Incident this knowledge enriches (OpsMemory hub); the
                resulting experience and memory are linked to it.

        Returns:
            The stored (or reinforced) experience and what happened.
        """
        if extracted is None:
            extracted = await self._extract(content)

        duplicate = await self._find_duplicate(extracted)
        if duplicate is not None:
            return await self._reinforce(duplicate, incident_id=incident_id)

        technologies = extract_technologies(content)
        async with self._session_factory() as session:
            experience = OperationalExperience(
                problem=extracted.problem,
                symptoms=extracted.symptoms,
                root_cause=extracted.root_cause,
                resolution=extracted.resolution,
                lessons_learned=extracted.lessons_learned,
                confidence=0.6,  # unverified single contribution (PRD confidence model)
                source=source,
                author=author,
                related_technologies=technologies,
                incident_id=incident_id,
            )
            session.add(experience)
            await session.commit()
            experience_id = experience.id

        await self._memory.add(
            [
                MemoryItem(
                    kind=MemoryKind.EXPERIENCE,
                    content=_experience_text(extracted),
                    confidence=0.6,
                    experience_id=experience_id,
                    incident_id=incident_id,
                    meta={"author": author or "", "technologies": technologies},
                )
            ]
        )
        for technology in technologies:
            await self._graph.upsert_edge(
                GraphEdge(
                    source=f"experience:{extracted.problem[:80]}",
                    relation="references",
                    target=technology,
                )
            )

        return TeachingResult(
            experience_id=experience_id,
            created=True,
            problem=extracted.problem,
            root_cause=extracted.root_cause,
            resolution=extracted.resolution,
            lessons_learned=extracted.lessons_learned,
            confidence=0.6,
            message="New operational experience learned.",
        )

    async def _extract(self, content: str) -> ExtractedExperience:
        """Structure the contribution via LLM, falling back to heuristics."""
        if self._llm is not None:
            try:
                raw = await self._llm.complete(
                    _EXTRACTION_PROMPT, content, max_tokens=self._llm_max_tokens
                )
                data = json.loads(_strip_fences(raw))
                if isinstance(data, dict) and data.get("problem"):
                    return ExtractedExperience(
                        problem=str(data["problem"]),
                        symptoms=[str(s) for s in data.get("symptoms") or []],
                        root_cause=_opt(data.get("root_cause")),
                        resolution=_opt(data.get("resolution")),
                        lessons_learned=_opt(data.get("lessons_learned")),
                    )
            except Exception as exc:
                logger.warning("LLM extraction failed, using heuristics: %s", exc)
        return _heuristic_extract(content)

    async def _find_duplicate(self, extracted: ExtractedExperience) -> OperationalExperience | None:
        """Semantic duplicate detection against existing experiences."""
        matches = await self._memory.search(
            _experience_text(extracted), limit=1, kinds=[MemoryKind.EXPERIENCE]
        )
        if not matches or matches[0].score < _DUPLICATE_THRESHOLD:
            return None
        experience_id = matches[0].experience_id
        if experience_id is None:
            return None
        async with self._session_factory() as session:
            return (
                await session.execute(
                    select(OperationalExperience).where(OperationalExperience.id == experience_id)
                )
            ).scalar_one_or_none()

    async def _reinforce(
        self, experience: OperationalExperience, *, incident_id: uuid.UUID | None = None
    ) -> TeachingResult:
        """Boost confidence of an existing experience instead of duplicating it.

        When the reinforcement arrives from an incident that the experience
        is not yet linked to, adopt that incident (the same lesson now has
        cross-incident support).
        """
        async with self._session_factory() as session:
            merged = await session.merge(experience)
            merged.confidence = min(0.95, merged.confidence + 0.05)
            if incident_id is not None and merged.incident_id is None:
                merged.incident_id = incident_id
            await session.commit()
            return TeachingResult(
                experience_id=merged.id,
                created=False,
                problem=merged.problem,
                root_cause=merged.root_cause,
                resolution=merged.resolution,
                lessons_learned=merged.lessons_learned,
                confidence=merged.confidence,
                duplicate_of=merged.id,
                message=(
                    "This matches an existing operational experience — its confidence "
                    f"was reinforced to {merged.confidence:.2f}."
                ),
            )


def _experience_text(extracted: ExtractedExperience) -> str:
    """Canonical text form of an experience for embedding and duplicate checks."""
    parts = [f"Problem: {extracted.problem}"]
    if extracted.root_cause:
        parts.append(f"Root cause: {extracted.root_cause}")
    if extracted.resolution:
        parts.append(f"Resolution: {extracted.resolution}")
    if extracted.lessons_learned:
        parts.append(f"Lesson: {extracted.lessons_learned}")
    return "\n".join(parts)


def _heuristic_extract(content: str) -> ExtractedExperience:
    """Deterministic extraction used when no LLM is configured."""
    text = " ".join(content.split())
    problem = text[:200]
    root_cause = _search_after(
        text, r"(?:because|caused by|root cause (?:was|is))\s+(.{10,200}?)(?:\.|$)"
    )
    resolution = _search_after(
        text,
        r"(?:resolved by|fixed by|we (?:fixed|solved|resolved) (?:this|it) by"
        r"|solution was)\s+(.{10,200}?)(?:\.|$)",
    )
    lesson = _search_after(
        text,
        r"(?:lesson(?: learned)?:?|in future,?|going forward,?)\s+(.{10,200}?)(?:\.|$)",
    )
    first_sentence = re.split(r"(?<=[.!?])\s", text, maxsplit=1)[0]
    return ExtractedExperience(
        problem=first_sentence[:200] or problem,
        root_cause=root_cause,
        resolution=resolution,
        lessons_learned=lesson,
    )


def _search_after(text: str, pattern: str) -> str | None:
    """Return the first capture group of a case-insensitive search."""
    match = re.search(pattern, text, re.IGNORECASE)
    return match.group(1).strip() if match else None


def _strip_fences(raw: str) -> str:
    """Remove markdown code fences around a JSON payload."""
    stripped = raw.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```[a-z]*\n?", "", stripped)
        stripped = re.sub(r"\n?```$", "", stripped)
    return stripped


def _opt(value: object) -> str | None:
    """Coerce possibly-null JSON values to optional strings."""
    if value is None or value == "":
        return None
    return str(value)
