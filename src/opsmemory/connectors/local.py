"""Local files connector: ingest documentation from a filesystem directory."""

import hashlib
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

from opsmemory.connectors.base import BaseConnector
from opsmemory.core.errors import ConnectorError
from opsmemory.domain.enums import ConnectorType, DocumentSource
from opsmemory.processing.models import RawContent

_EXTENSIONS = {
    ".md": "markdown",
    ".markdown": "markdown",
    ".txt": "text",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".html": "html",
}


class LocalFilesConnector(BaseConnector):
    """Ingests Markdown/YAML/JSON/TXT/HTML files from a local directory.

    Config:
        path: Directory to ingest (required).

    Checkpoint:
        Mapping of relative path → content SHA-256, so unchanged files are
        skipped on subsequent runs.
    """

    type = ConnectorType.LOCAL_FILES
    source = DocumentSource.LOCAL_FILES

    @property
    def _root(self) -> Path:
        path = self.config.get("path")
        if not path:
            raise ConnectorError("local_files connector requires a 'path' config value")
        return Path(path).expanduser().resolve()

    async def discover(self) -> AsyncIterator[RawContent]:
        """Yield every new or modified supported file under the root."""
        root = self._root
        if not root.is_dir():
            raise ConnectorError(f"Ingest path is not a directory: {root}")
        hashes: dict[str, str] = dict(self.checkpoint.get("hashes", {}))
        for file in sorted(root.rglob("*")):
            if not file.is_file() or file.suffix.lower() not in _EXTENSIONS:
                continue
            if any(part.startswith(".") for part in file.relative_to(root).parts):
                continue
            try:
                text = file.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            relative = str(file.relative_to(root))
            digest = hashlib.sha256(text.encode()).hexdigest()
            if hashes.get(relative) == digest:
                continue
            hashes[relative] = digest
            yield RawContent(
                identifier=relative,
                content=text,
                content_type=_EXTENSIONS[file.suffix.lower()],
                url=file.as_uri(),
                last_modified=datetime.fromtimestamp(file.stat().st_mtime, tz=UTC),
                metadata={"absolute_path": str(file)},
            )
        self.checkpoint["hashes"] = hashes

    async def health(self) -> tuple[bool, str]:
        """Healthy when the configured directory exists."""
        try:
            root = self._root
        except ConnectorError as exc:
            return False, exc.message
        if root.is_dir():
            return True, f"directory {root} accessible"
        return False, f"directory {root} does not exist"
