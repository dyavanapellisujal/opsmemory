"""Deterministic relationship identification (PRD pipeline Stage 5).

Relationships are extracted with pattern matching against known entity names
and explicit dependency phrases — no LLM involved. The graph layer projects
these into the knowledge graph.
"""

import re

from opsmemory.processing.models import ExtractedRelationship, NormalizedDocument

_DEPENDS_ON = re.compile(
    r"\b([a-z0-9][a-z0-9._-]{1,60}?)\s+depends\s+on\s+([a-z0-9][a-z0-9._-]{1,60})\b",
    re.IGNORECASE,
)

_TECHNOLOGIES = (
    "redis",
    "kafka",
    "postgres",
    "postgresql",
    "mysql",
    "nginx",
    "rabbitmq",
    "elasticsearch",
    "kubernetes",
    "terraform",
    "helm",
    "docker",
    "prometheus",
    "grafana",
)


def extract_relationships(
    document: NormalizedDocument, known_services: list[str]
) -> list[ExtractedRelationship]:
    """Extract relationships from a normalized document.

    Args:
        document: The document to analyze.
        known_services: Service names already known to the platform; mentions
            create ``documented_by`` edges.

    Returns:
        Deduplicated relationships found in the content.
    """
    relationships: list[ExtractedRelationship] = []
    lowered = document.content.lower()

    for service in known_services:
        if re.search(rf"\b{re.escape(service.lower())}\b", lowered):
            relationships.append(
                ExtractedRelationship(
                    source_name=service,
                    relation="documented_by",
                    target_name=document.title,
                    target_kind="document",
                )
            )

    for match in _DEPENDS_ON.finditer(document.content):
        relationships.append(
            ExtractedRelationship(
                source_name=match.group(1).lower(),
                relation="depends_on",
                target_name=match.group(2).lower(),
            )
        )

    return _dedupe(relationships)


def extract_technologies(text: str) -> list[str]:
    """Return well-known technologies mentioned in the text."""
    lowered = text.lower()
    return [t for t in _TECHNOLOGIES if re.search(rf"\b{re.escape(t)}\b", lowered)]


def _dedupe(items: list[ExtractedRelationship]) -> list[ExtractedRelationship]:
    """Remove duplicate relationships while preserving order."""
    seen: set[tuple[str, str, str]] = set()
    unique: list[ExtractedRelationship] = []
    for item in items:
        key = (item.source_name.lower(), item.relation, item.target_name.lower())
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique
