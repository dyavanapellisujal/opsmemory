"""Tests for the connector framework (local files, HTTP docs, registry)."""

from pathlib import Path

import pytest
import respx
from httpx import Response

from opsmemory.connectors.http import HttpDocsConnector
from opsmemory.connectors.local import LocalFilesConnector
from opsmemory.connectors.registry import available_types, build_connector
from opsmemory.core.errors import ConnectorError
from opsmemory.domain.enums import ConnectorType
from opsmemory.processing.models import RawContent


async def _collect(connector: LocalFilesConnector | HttpDocsConnector) -> list[RawContent]:
    return [raw async for raw in connector.discover()]


async def test_local_connector_discovers_and_checkpoints(tmp_path: Path) -> None:
    (tmp_path / "runbook.md").write_text("# Runbook\ncontent")
    (tmp_path / "notes.txt").write_text("plain notes")
    (tmp_path / "image.png").write_bytes(b"\x89PNG")
    (tmp_path / ".hidden").mkdir()
    (tmp_path / ".hidden" / "secret.md").write_text("# hidden")

    connector = LocalFilesConnector(config={"path": str(tmp_path)}, checkpoint={})
    first = await _collect(connector)
    assert sorted(r.identifier for r in first) == ["notes.txt", "runbook.md"]

    # Second run with the produced checkpoint sees no changes.
    second_connector = LocalFilesConnector(
        config={"path": str(tmp_path)}, checkpoint=connector.checkpoint
    )
    assert await _collect(second_connector) == []

    # Modifying a file makes only that file reappear.
    (tmp_path / "runbook.md").write_text("# Runbook v2")
    third_connector = LocalFilesConnector(
        config={"path": str(tmp_path)}, checkpoint=second_connector.checkpoint
    )
    third = await _collect(third_connector)
    assert [r.identifier for r in third] == ["runbook.md"]


async def test_local_connector_health(tmp_path: Path) -> None:
    ok, _ = await LocalFilesConnector(config={"path": str(tmp_path)}, checkpoint={}).health()
    assert ok
    bad, message = await LocalFilesConnector(
        config={"path": str(tmp_path / "nope")}, checkpoint={}
    ).health()
    assert not bad and "does not exist" in message


async def test_local_connector_requires_path() -> None:
    connector = LocalFilesConnector(config={}, checkpoint={})
    with pytest.raises(ConnectorError):
        await _collect(connector)


@respx.mock
async def test_http_connector_crawls_same_host_only() -> None:
    respx.get("https://docs.example.com").mock(
        return_value=Response(
            200,
            headers={"content-type": "text/html"},
            text=(
                '<html><body><h1>Home</h1><a href="/guide">guide</a>'
                '<a href="https://other.example.org/x">external</a></body></html>'
            ),
        )
    )
    respx.get("https://docs.example.com/guide").mock(
        return_value=Response(
            200,
            headers={"content-type": "text/html"},
            text="<html><body><h1>Guide</h1><p>How to deploy.</p></body></html>",
        )
    )
    connector = HttpDocsConnector(
        config={"url": "https://docs.example.com", "max_pages": 10}, checkpoint={}
    )
    pages = await _collect(connector)
    identifiers = {p.identifier for p in pages}
    assert identifiers == {"https://docs.example.com", "https://docs.example.com/guide"}

    # Unchanged pages are skipped on the next crawl via the checkpoint.
    again = HttpDocsConnector(
        config={"url": "https://docs.example.com", "max_pages": 10},
        checkpoint=connector.checkpoint,
    )
    assert await _collect(again) == []


def test_registry_builds_known_and_rejects_unknown() -> None:
    connector = build_connector(ConnectorType.LOCAL_FILES, {"path": "/tmp"}, {})
    assert isinstance(connector, LocalFilesConnector)
    assert available_types() == ["http_docs", "local_files"]
    with pytest.raises(ConnectorError, match="github"):
        build_connector(ConnectorType.GITHUB, {}, {})
