"""Chat service: the Retrieval-Oriented Agent (PRD AI Agent Architecture).

The platform classifies the request, retrieves and ranks evidence, and
assembles the context package. The LLM only reasons over that curated
context. Teaching messages are routed to the Teaching Pipeline and never
trigger retrieval. Without an LLM configured, answers degrade gracefully to
extractive summaries of the best evidence.
"""

import uuid

from pydantic import BaseModel, Field

from opsmemory.ai.base import LLMProvider
from opsmemory.core.logging import get_logger
from opsmemory.retrieval.classifier import Intent, classify
from opsmemory.retrieval.engine import ContextPackage, RetrievalEngine
from opsmemory.teaching.service import TeachingService

logger = get_logger(__name__)

_SYSTEM_PROMPT = """You are OpsMemory, the operational memory of an engineering organization.
Answer the engineer's question using ONLY the evidence provided. Rules:
- Never invent incidents, owners, architecture decisions, or procedures.
- Ground every significant statement in the provided evidence.
- If the evidence is insufficient, say so plainly and suggest what to ingest or teach.
- Prefer operational experiences (real lessons) over documentation when both apply.
- Be concise and practical; use short paragraphs or bullets."""


class Citation(BaseModel):
    """A reference to a piece of supporting evidence."""

    kind: str = Field(description='"document", "experience", "memory", or "graph".')
    id: uuid.UUID | None = None
    title: str
    url: str | None = None


class ChatResponse(BaseModel):
    """Structured chat answer (PRD Response Structure)."""

    answer: str
    intent: Intent
    confidence: float = Field(ge=0.0, le=1.0)
    citations: list[Citation] = Field(default_factory=list)
    taught: bool = Field(default=False, description="True when routed to teaching.")


class ChatService:
    """Deterministic orchestration around LLM reasoning."""

    def __init__(
        self,
        retrieval: RetrievalEngine,
        teaching: TeachingService,
        llm: LLMProvider | None,
        llm_max_tokens: int = 2048,
    ) -> None:
        self._retrieval = retrieval
        self._teaching = teaching
        self._llm = llm
        self._llm_max_tokens = llm_max_tokens

    async def chat(self, message: str, *, author: str | None = None) -> ChatResponse:
        """Handle a chat message: teach or retrieve-then-reason."""
        if classify(message) is Intent.TEACHING:
            result = await self._teaching.teach(message, author=author)
            return ChatResponse(
                answer=result.message
                + (f"\n\nProblem: {result.problem}" if result.created else ""),
                intent=Intent.TEACHING,
                confidence=result.confidence,
                citations=[
                    Citation(kind="experience", id=result.experience_id, title=result.problem)
                ],
                taught=True,
            )

        package = await self._retrieval.retrieve(message)
        if package.is_empty:
            return ChatResponse(
                answer=(
                    "I don't have any organizational knowledge relevant to this yet. "
                    "Ingest related documentation (`opsmemory ingest ...`) or teach me "
                    "what you know (`opsmemory teach ...`)."
                ),
                intent=package.intent,
                confidence=0.0,
            )

        citations = _citations(package)
        confidence = _confidence(package, llm_available=self._llm is not None)

        if self._llm is None:
            return ChatResponse(
                answer=_extractive_answer(package),
                intent=package.intent,
                confidence=confidence,
                citations=citations,
            )

        try:
            answer = await self._llm.complete(
                _SYSTEM_PROMPT,
                _render_context(package),
                max_tokens=self._llm_max_tokens,
            )
        except Exception as exc:
            logger.warning("LLM reasoning failed, falling back to extractive answer: %s", exc)
            answer = _extractive_answer(package)
            confidence = min(confidence, 0.4)

        return ChatResponse(
            answer=answer.strip(),
            intent=package.intent,
            confidence=confidence,
            citations=citations,
        )


def _render_context(package: ContextPackage) -> str:
    """Serialize the context package into the user prompt for the LLM."""
    lines = [f"QUESTION: {package.query}", ""]
    if package.services:
        lines.append("SERVICES:")
        for service in package.services:
            owner = f" (owner: {service.owner_team})" if service.owner_team else ""
            lines.append(f"- {service.name}{owner}: {service.description or 'no description'}")
    if package.graph_facts:
        lines.append("\nRELATIONSHIPS:")
        lines.extend(
            f"- {edge.source} --{edge.relation}--> {edge.target}"
            for edge in package.graph_facts[:20]
        )
    if package.experiences:
        lines.append("\nOPERATIONAL EXPERIENCES (highest value evidence):")
        for exp in package.experiences:
            lines.append(f"- Problem: {exp.problem}")
            if exp.root_cause:
                lines.append(f"  Root cause: {exp.root_cause}")
            if exp.resolution:
                lines.append(f"  Resolution: {exp.resolution}")
            if exp.lessons_learned:
                lines.append(f"  Lesson: {exp.lessons_learned}")
            lines.append(f"  Confidence: {exp.confidence:.2f}")
    if package.memories:
        lines.append("\nSEMANTIC MEMORIES:")
        for memory in package.memories:
            section = f" [{memory.section}]" if memory.section else ""
            lines.append(f"- (score {memory.score:.2f}){section} {memory.content[:600]}")
    if package.documents:
        lines.append("\nDOCUMENTS:")
        for doc in package.documents:
            lines.append(f"- {doc.title} ({doc.source}): {doc.snippet}")
    return "\n".join(lines)


def _extractive_answer(package: ContextPackage) -> str:
    """Best-evidence summary used when no LLM is configured or it fails."""
    lines: list[str] = []
    if package.experiences:
        exp = package.experiences[0]
        lines.append(f"Closest operational experience: {exp.problem}")
        if exp.resolution:
            lines.append(f"Previous resolution: {exp.resolution}")
        if exp.lessons_learned:
            lines.append(f"Lesson learned: {exp.lessons_learned}")
    if package.graph_facts:
        lines.append("Known relationships:")
        lines.extend(f"  {e.source} --{e.relation}--> {e.target}" for e in package.graph_facts[:10])
    if package.services and not package.graph_facts:
        for service in package.services:
            owner = f" — owned by {service.owner_team}" if service.owner_team else ""
            lines.append(f"Service {service.name}{owner}.")
    if package.memories and not lines:
        lines.append(package.memories[0].content[:500])
    if package.documents:
        lines.append("Relevant documents: " + ", ".join(d.title for d in package.documents[:5]))
    lines.append("\n(No LLM configured — this is an extractive summary of the evidence.)")
    return "\n".join(lines)


def _citations(package: ContextPackage) -> list[Citation]:
    """Build the citation list from every evidence type in the package."""
    citations: list[Citation] = []
    for exp in package.experiences:
        citations.append(Citation(kind="experience", id=exp.id, title=exp.problem))
    for doc in package.documents:
        citations.append(Citation(kind="document", id=doc.id, title=doc.title, url=doc.url))
    seen_docs = {c.id for c in citations}
    for memory in package.memories:
        if memory.document_id is not None and memory.document_id not in seen_docs:
            title = str(memory.meta.get("document_title") or memory.section or "memory")
            citations.append(Citation(kind="memory", id=memory.document_id, title=title))
            seen_docs.add(memory.document_id)
    return citations[:10]


def _confidence(package: ContextPackage, *, llm_available: bool) -> float:
    """Heuristic confidence from evidence quantity, similarity, and source quality."""
    score = 0.0
    if package.memories:
        score += 0.4 * max(m.score for m in package.memories)
    if package.experiences:
        score += 0.3 * max(e.confidence for e in package.experiences)
    if package.graph_facts or package.services:
        score += 0.2
    if package.documents:
        score += 0.1
    if not llm_available:
        score *= 0.8
    return round(min(score, 0.95), 2)
