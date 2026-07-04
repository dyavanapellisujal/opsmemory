"""Extract text from uploaded knowledge files (Markdown, TXT, PDF).

Uploaded incident evidence arrives as real files; this turns them into the
plain text / markdown the processing pipeline already understands.
"""

import io

from opsmemory.core.errors import ValidationFailedError

_MAX_BYTES = 10 * 1024 * 1024  # 10 MB safety cap

_TEXT_EXTS = {"md": "markdown", "markdown": "markdown", "txt": "text", "text": "text"}


def extract_upload(filename: str, data: bytes) -> tuple[str, str]:
    """Extract ``(text, content_type)`` from an uploaded file.

    Supports Markdown, plain text, and PDF (text-based). Raises
    :class:`ValidationFailedError` for unsupported types, oversize files, or
    PDFs with no extractable text (e.g. scanned images).
    """
    if len(data) > _MAX_BYTES:
        raise ValidationFailedError(
            f"File exceeds the {_MAX_BYTES // (1024 * 1024)} MB limit", code="FILE_TOO_LARGE"
        )
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext == "pdf":
        return _extract_pdf(data), "text"
    if ext in _TEXT_EXTS:
        return _decode(data), _TEXT_EXTS[ext]
    # Unknown extension: accept if it decodes cleanly as UTF-8 text.
    try:
        return data.decode("utf-8"), "text"
    except UnicodeDecodeError as exc:
        raise ValidationFailedError(
            f"Unsupported file type {ext!r}; upload Markdown, TXT, or PDF",
            code="UNSUPPORTED_FILE_TYPE",
        ) from exc


def _decode(data: bytes) -> str:
    """Decode text bytes, tolerating a BOM and invalid bytes."""
    return data.decode("utf-8-sig", errors="replace")


def _extract_pdf(data: bytes) -> str:
    """Extract text from a PDF's pages using pypdf."""
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(data))
        text = "\n\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as exc:  # malformed / encrypted PDF
        raise ValidationFailedError(
            f"Could not read the PDF: {exc}", code="PDF_UNREADABLE"
        ) from exc
    if not text.strip():
        raise ValidationFailedError(
            "The PDF has no extractable text (scanned image?); upload a text-based PDF",
            code="PDF_NO_TEXT",
        )
    return text
