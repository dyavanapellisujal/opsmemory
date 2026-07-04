"""Tests for uploading real files (Markdown/TXT/PDF) into an incident."""

import io

import pytest
from httpx import AsyncClient

from opsmemory.core.errors import ValidationFailedError
from opsmemory.processing.files import extract_upload


async def _incident(client: AsyncClient, title: str) -> str:
    r = await client.post("/api/v1/incidents", json={"title": title, "severity": "sev3"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def test_upload_markdown_file(client: AsyncClient) -> None:
    iid = await _incident(client, "Redis outage")
    content = b"# Redis Recovery\n\nRotate the `redis-credentials` secret and restart."
    resp = await client.post(
        f"/api/v1/incidents/{iid}/documents/upload",
        files={"file": ("runbook.md", content, "text/markdown")},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["memories_added"] >= 1

    detail = (await client.get(f"/api/v1/incidents/{iid}")).json()
    assert detail["counts"]["documents"] == 1
    assert any(d["label"] == "runbook.md" for d in detail["documents"])
    detailed = next(
        s for s in detail["documentation"]["sections"] if s["key"] == "detailed_summary"
    )
    assert any("redis-credentials" in item for item in detailed["items"])


async def test_upload_txt_with_title_override(client: AsyncClient) -> None:
    iid = await _incident(client, "Kafka lag")
    resp = await client.post(
        f"/api/v1/incidents/{iid}/documents/upload",
        files={"file": ("notes.txt", b"consumer group rebalance storm", "text/plain")},
        data={"title": "Kafka postmortem notes"},
    )
    assert resp.status_code == 201
    detail = (await client.get(f"/api/v1/incidents/{iid}")).json()
    assert any(d["label"] == "Kafka postmortem notes" for d in detail["documents"])


async def test_upload_unsupported_type_rejected(client: AsyncClient) -> None:
    iid = await _incident(client, "Bad upload")
    resp = await client.post(
        f"/api/v1/incidents/{iid}/documents/upload",
        files={"file": ("logo.png", b"\x89PNG\r\n\x1a\n\x00\x01", "image/png")},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"


def test_extract_markdown_and_txt() -> None:
    text, ctype = extract_upload("runbook.md", b"# Title\ncontent")
    assert ctype == "markdown" and "Title" in text
    text, ctype = extract_upload("notes.txt", b"plain text")
    assert ctype == "text" and text == "plain text"


def test_extract_pdf_roundtrip() -> None:
    pypdf = pytest.importorskip("pypdf")
    buf = io.BytesIO()
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.write(buf)
    # A blank PDF has no extractable text → should raise, not crash.
    with pytest.raises(ValidationFailedError) as exc:
        extract_upload("scan.pdf", buf.getvalue())
    assert exc.value.code == "PDF_NO_TEXT"


def test_extract_rejects_oversize() -> None:
    with pytest.raises(ValidationFailedError) as exc:
        extract_upload("big.txt", b"x" * (11 * 1024 * 1024))
    assert exc.value.code == "FILE_TOO_LARGE"
