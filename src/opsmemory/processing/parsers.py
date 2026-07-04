"""Document parsers: convert raw connector content into normalized documents.

Parsing is deterministic — no LLMs are involved at this stage
("Deterministic First", PRD processing principles).
"""

import json
import re
from pathlib import PurePosixPath

import html2text
import yaml
from bs4 import BeautifulSoup

from opsmemory.domain.enums import DocumentSource
from opsmemory.processing.models import NormalizedDocument, RawContent

_MD_HEADING = re.compile(r"^#\s+(.+)$", re.MULTILINE)


def parse(raw: RawContent, source: DocumentSource) -> NormalizedDocument:
    """Parse raw content into a normalized document.

    Args:
        raw: Content fetched by a connector.
        source: Which source system produced it.

    Returns:
        A normalized, source-agnostic document.
    """
    content_type = raw.content_type.lower()
    if content_type == "html":
        title, content = _parse_html(raw.content)
    elif content_type in {"yaml", "yml"}:
        title, content = _parse_structured(raw.content, raw.identifier, kind="yaml")
    elif content_type == "json":
        title, content = _parse_structured(raw.content, raw.identifier, kind="json")
    else:  # markdown and plain text
        title, content = _parse_markdown(raw.content)

    return NormalizedDocument(
        identifier=raw.identifier,
        title=raw.title_hint or title or _title_from_identifier(raw.identifier),
        content=content.strip(),
        source=source,
        url=raw.url,
        last_modified=raw.last_modified,
        tags=_tags_from_identifier(raw.identifier),
        metadata=dict(raw.metadata),
    )


def _parse_markdown(text: str) -> tuple[str | None, str]:
    """Extract the first H1 as title; content passes through unchanged."""
    match = _MD_HEADING.search(text)
    return (match.group(1).strip() if match else None), text


def _parse_html(html: str) -> tuple[str | None, str]:
    """Strip navigation/script noise and convert HTML to markdown text."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
        tag.decompose()
    title = soup.title.get_text(strip=True) if soup.title else None
    h1 = soup.find("h1")
    if h1 is not None:
        title = h1.get_text(strip=True) or title
    converter = html2text.HTML2Text()
    converter.ignore_images = True
    converter.body_width = 0
    return title, converter.handle(str(soup))


def _parse_structured(text: str, identifier: str, *, kind: str) -> tuple[str | None, str]:
    """Validate YAML/JSON and render it as a fenced code block for retrieval."""
    try:
        data = yaml.safe_load(text) if kind == "yaml" else json.loads(text)
    except (yaml.YAMLError, json.JSONDecodeError):
        return None, text
    pretty = yaml.safe_dump(data, sort_keys=False) if kind == "yaml" else json.dumps(data, indent=2)
    title = None
    if isinstance(data, dict):
        meta = data.get("metadata")
        if isinstance(meta, dict) and isinstance(meta.get("name"), str):
            title = meta["name"]  # Kubernetes-style manifests
        elif isinstance(data.get("name"), str):
            title = data["name"]
    return title, f"```{kind}\n{pretty}```"


def _title_from_identifier(identifier: str) -> str:
    """Derive a readable title from a path or URL."""
    stem = PurePosixPath(identifier.rstrip("/").split("?")[0]).stem or identifier
    return stem.replace("-", " ").replace("_", " ").strip().title() or identifier


def _tags_from_identifier(identifier: str) -> list[str]:
    """Derive tags from well-known path segments (adr, runbook, incident...)."""
    lowered = identifier.lower()
    tags = [
        tag
        for tag in ("adr", "runbook", "incident", "postmortem", "architecture", "terraform", "helm")
        if tag in lowered
    ]
    if "readme" in lowered:
        tags.append("readme")
    return tags
