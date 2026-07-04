"""Semantic chunking: split documents on heading boundaries, not token counts."""

import re

from opsmemory.processing.models import Chunk

_HEADING = re.compile(r"^(#{1,4})\s+(.+)$", re.MULTILINE)
_MAX_CHUNK_CHARS = 4000
_MIN_CHUNK_CHARS = 40


def chunk_document(content: str, *, title: str = "") -> list[Chunk]:
    """Split document content into semantically meaningful chunks.

    Markdown headings are the preferred boundaries (PRD Stage 4); oversized
    sections are further split on paragraph boundaries. Tiny fragments are
    merged into their predecessor.

    Args:
        content: Normalized document content.
        title: Document title, used as the root section name.

    Returns:
        Ordered chunks with section paths and positions.
    """
    sections = _split_by_headings(content, root=title or "Document")
    chunks: list[Chunk] = []
    for section_name, text in sections:
        for piece in _split_oversized(text):
            body = piece.strip()
            if not body:
                continue
            if len(body) < _MIN_CHUNK_CHARS and chunks:
                previous = chunks[-1]
                chunks[-1] = Chunk(
                    section=previous.section,
                    position=previous.position,
                    content=previous.content + "\n\n" + body,
                )
                continue
            chunks.append(Chunk(section=section_name, position=len(chunks), content=body))
    return chunks


def _split_by_headings(content: str, *, root: str) -> list[tuple[str, str]]:
    """Split content into (section-path, text) pairs at markdown headings."""
    matches = list(_HEADING.finditer(content))
    if not matches:
        return [(root, content)]

    sections: list[tuple[str, str]] = []
    preamble = content[: matches[0].start()].strip()
    if preamble:
        sections.append((root, preamble))

    # Track the heading hierarchy so section names carry their parent path.
    stack: list[tuple[int, str]] = []
    for i, match in enumerate(matches):
        level, heading = len(match.group(1)), match.group(2).strip()
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, heading))
        path = " > ".join(name for _, name in stack)
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        body = content[match.end() : end].strip()
        text = f"{'#' * level} {heading}\n{body}" if body else f"{'#' * level} {heading}"
        sections.append((path, text))
    return sections


def _split_oversized(text: str) -> list[str]:
    """Split a section exceeding the chunk budget on paragraph boundaries."""
    if len(text) <= _MAX_CHUNK_CHARS:
        return [text]
    pieces: list[str] = []
    current: list[str] = []
    size = 0
    for paragraph in text.split("\n\n"):
        if size + len(paragraph) > _MAX_CHUNK_CHARS and current:
            pieces.append("\n\n".join(current))
            current, size = [], 0
        current.append(paragraph)
        size += len(paragraph) + 2
    if current:
        pieces.append("\n\n".join(current))
    return pieces
