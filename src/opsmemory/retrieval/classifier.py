"""Deterministic request/intent classification (PRD Workflow Engine, Step 1).

Classification never uses an LLM: it is the routing layer that decides which
pipeline (teaching vs retrieval) and which retrieval strategies run.
"""

import re
from enum import StrEnum


class Intent(StrEnum):
    """Classified purpose of a user request."""

    TEACHING = "teaching"
    OWNERSHIP = "ownership"
    DEPENDENCY = "dependency"
    HISTORICAL = "historical"
    KNOWLEDGE = "knowledge"


_TEACHING = re.compile(
    r"\b(remember this|save this|learn this|teach you|lesson learned|note for the future"
    r"|we (fixed|solved|resolved) (this|it|the)|was (fixed|solved|resolved) by"
    r"|root cause was|the fix was)\b",
    re.IGNORECASE,
)
_OWNERSHIP = re.compile(
    r"\b(who owns?|owner of|which team|who maintains?|responsible for)\b", re.IGNORECASE
)
_DEPENDENCY = re.compile(
    r"\b(depends? on|dependenc\w+|which services? (use|rely)|downstream|upstream)\b",
    re.IGNORECASE,
)
_HISTORICAL = re.compile(
    r"\b(have we (seen|experienced|solved|had)|happened before"
    r"|previous(ly)? (incident|outage|failure)"
    r"|similar (incident|issue|problem|outage)|in the past)\b",
    re.IGNORECASE,
)


def classify(text: str) -> Intent:
    """Classify a user request into an intent.

    Teaching is checked first so contributions are never misrouted into
    retrieval (PRD: "Teaching requests never trigger unnecessary retrieval").
    """
    if _TEACHING.search(text):
        return Intent.TEACHING
    if _OWNERSHIP.search(text):
        return Intent.OWNERSHIP
    if _DEPENDENCY.search(text):
        return Intent.DEPENDENCY
    if _HISTORICAL.search(text):
        return Intent.HISTORICAL
    return Intent.KNOWLEDGE
