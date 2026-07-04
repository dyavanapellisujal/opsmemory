"""LLM-powered incident knowledge extraction from meeting transcripts.

Uses the dedicated SRE system prompt
(``incident_meeting_extraction_prompt.txt``) to produce structured,
reusable operational knowledge — never a generic meeting summary.

The extraction is consumed by :class:`~opsmemory.services.meetings.MeetingService`
which feeds the result into the Teaching Pipeline, Memory Engine, and
Knowledge Graph.
"""

import json
import re
from typing import Any

from pydantic import BaseModel, Field

from opsmemory.agent.prompts import load_prompt
from opsmemory.ai.base import LLMProvider
from opsmemory.core.logging import get_logger
from opsmemory.domain.enums import IncidentSeverity, IncidentStatus

logger = get_logger(__name__)

_PROMPT_FILE = "incident_meeting_extraction_prompt.txt"

# ---------------------------------------------------------------------------
# Pydantic models matching the JSON schema in the SRE extraction prompt
# ---------------------------------------------------------------------------


class IncidentExtraction(BaseModel):
    """Structured incident metadata extracted from a meeting transcript."""

    title: str = ""
    severity: str = "sev3"
    status: str = "open"
    timeline: list[str] = Field(default_factory=list)

    def severity_enum(self) -> IncidentSeverity:
        """Map the free-text severity to a domain enum, defaulting to sev3."""
        mapping = {s.value: s for s in IncidentSeverity}
        return mapping.get(self.severity.lower().strip(), IncidentSeverity.SEV3)

    def status_enum(self) -> IncidentStatus:
        """Map the free-text status to a domain enum, defaulting to open."""
        mapping = {s.value: s for s in IncidentStatus}
        return mapping.get(self.status.lower().strip(), IncidentStatus.OPEN)


class ActionItemExtraction(BaseModel):
    """A single action item with an optional owner."""

    owner: str | None = None
    task: str = ""


class OpExExtraction(BaseModel):
    """Consolidated operational experience (problem → resolution → lesson)."""

    problem: str | None = None
    resolution: str | None = None
    lesson: str | None = None


class MeetingExtraction(BaseModel):
    """Complete extraction result matching the SRE prompt's JSON schema.

    Every field defaults to a safe empty value so partial LLM responses
    and fallback extraction still produce a valid object.
    """

    meeting_summary: str = ""
    incident: IncidentExtraction | None = None
    services: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)
    root_cause: str | None = None
    contributing_factors: list[str] = Field(default_factory=list)
    resolution: list[str] = Field(default_factory=list)
    preventative_actions: list[str] = Field(default_factory=list)
    lessons_learned: list[str] = Field(default_factory=list)
    action_items: list[ActionItemExtraction] = Field(default_factory=list)
    architecture_decisions: list[str] = Field(default_factory=list)
    operational_experience: OpExExtraction | None = None


# ---------------------------------------------------------------------------
# Extraction entry point
# ---------------------------------------------------------------------------


async def extract_incident_knowledge(
    llm: LLMProvider | None,
    transcript: str,
    *,
    max_tokens: int = 4096,
) -> MeetingExtraction:
    """Extract structured incident knowledge from a meeting transcript.

    Uses the dedicated SRE system prompt and falls back to a minimal
    extractive summary when no LLM is configured or the LLM fails.

    Args:
        llm: The LLM provider (``None`` triggers fallback mode).
        transcript: Speaker-attributed plain-text transcript.
        max_tokens: Response token budget for the LLM.

    Returns:
        Structured extraction as a :class:`MeetingExtraction`.
    """
    if llm is None:
        logger.info("No LLM configured — using fallback extraction")
        return _fallback_extraction(transcript)

    system_prompt = load_prompt(_PROMPT_FILE)
    try:
        raw = await llm.complete(system_prompt, transcript, max_tokens=max_tokens)
        data = json.loads(_strip_fences(raw))
        if not isinstance(data, dict):
            raise ValueError("LLM response is not a JSON object")
        return _parse_extraction(data)
    except Exception as exc:
        logger.warning(
            "LLM extraction failed, using fallback: %s",
            exc,
        )
        return _fallback_extraction(transcript)


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def _parse_extraction(data: dict[str, Any]) -> MeetingExtraction:
    """Parse a raw JSON dict into a validated MeetingExtraction model.

    Handles partial or slightly malformed LLM output gracefully by
    coercing values and using defaults for missing fields.
    """
    incident_raw = data.get("incident")
    incident = None
    if isinstance(incident_raw, dict) and incident_raw.get("title"):
        incident = IncidentExtraction(
            title=str(incident_raw.get("title", "")),
            severity=str(incident_raw.get("severity", "sev3")),
            status=str(incident_raw.get("status", "open")),
            timeline=[str(t) for t in (incident_raw.get("timeline") or []) if t],
        )

    action_items_raw = data.get("action_items") or []
    action_items = [
        ActionItemExtraction(
            owner=_opt(item.get("owner")) if isinstance(item, dict) else None,
            task=str(item.get("task", "")) if isinstance(item, dict) else str(item),
        )
        for item in action_items_raw
        if item
    ]

    opex_raw = data.get("operational_experience")
    opex = None
    if isinstance(opex_raw, dict) and (opex_raw.get("problem") or opex_raw.get("resolution")):
        opex = OpExExtraction(
            problem=_opt(opex_raw.get("problem")),
            resolution=_opt(opex_raw.get("resolution")),
            lesson=_opt(opex_raw.get("lesson")),
        )

    return MeetingExtraction(
        meeting_summary=str(data.get("meeting_summary") or ""),
        incident=incident,
        services=_str_list(data.get("services")),
        technologies=_str_list(data.get("technologies")),
        root_cause=_opt(data.get("root_cause")),
        contributing_factors=_str_list(data.get("contributing_factors")),
        resolution=_str_list(data.get("resolution")),
        preventative_actions=_str_list(data.get("preventative_actions")),
        lessons_learned=_str_list(data.get("lessons_learned")),
        action_items=action_items,
        architecture_decisions=_str_list(data.get("architecture_decisions")),
        operational_experience=opex,
    )


def _fallback_extraction(transcript: str) -> MeetingExtraction:
    """Produce a minimal extraction when no LLM is available.

    Uses the first 500 characters as the summary — downstream stages
    still function correctly with empty structured fields.
    """
    summary = " ".join(transcript.split())[:500]
    return MeetingExtraction(
        meeting_summary=summary or "No transcript content available.",
    )


def _strip_fences(raw: str) -> str:
    """Remove markdown code fences around a JSON payload."""
    stripped = raw.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```[a-z]*\n?", "", stripped)
        stripped = re.sub(r"\n?```$", "", stripped)
    return stripped


def _opt(value: object) -> str | None:
    """Coerce possibly-null JSON values to optional strings."""
    if value is None or value == "" or value == "null":
        return None
    return str(value)


def _str_list(value: object) -> list[str]:
    """Coerce a JSON value to a list of non-empty strings."""
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item and str(item).strip()]
