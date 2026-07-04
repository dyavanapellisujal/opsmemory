"""HTTP documentation connector: crawl and ingest documentation websites."""

import hashlib
from collections.abc import AsyncIterator
from urllib.parse import urldefrag, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from opsmemory.connectors.base import BaseConnector
from opsmemory.core.errors import ConnectorError
from opsmemory.domain.enums import ConnectorType, DocumentSource
from opsmemory.processing.models import RawContent


class HttpDocsConnector(BaseConnector):
    """Crawls a documentation site, staying on the starting host.

    Config:
        url: Starting URL (required).
        max_pages: Page budget per sync (default 50).
        max_depth: Link depth from the start page (default 3).

    Checkpoint:
        Mapping of URL → content SHA-256 so unchanged pages are skipped.
    """

    type = ConnectorType.HTTP_DOCS
    source = DocumentSource.HTTP_DOCS

    @property
    def _start_url(self) -> str:
        url = self.config.get("url")
        if not url:
            raise ConnectorError("http_docs connector requires a 'url' config value")
        return str(url).rstrip("/")

    async def discover(self) -> AsyncIterator[RawContent]:
        """Breadth-first crawl of same-host documentation pages."""
        start = self._start_url
        max_pages = int(self.config.get("max_pages", 50))
        max_depth = int(self.config.get("max_depth", 3))
        host = urlparse(start).netloc
        hashes: dict[str, str] = dict(self.checkpoint.get("hashes", {}))

        queue: list[tuple[str, int]] = [(start, 0)]
        visited: set[str] = set()
        async with httpx.AsyncClient(
            timeout=15.0, follow_redirects=True, headers={"User-Agent": "OpsMemory/0.2"}
        ) as client:
            while queue and len(visited) < max_pages:
                url, depth = queue.pop(0)
                url = urldefrag(url).url
                if url in visited or urlparse(url).netloc != host:
                    continue
                visited.add(url)
                try:
                    response = await client.get(url)
                except httpx.HTTPError:
                    continue
                content_type = response.headers.get("content-type", "")
                if response.status_code != 200 or "text" not in content_type:
                    continue

                is_html = "html" in content_type
                if is_html and depth < max_depth:
                    soup = BeautifulSoup(response.text, "html.parser")
                    for anchor in soup.find_all("a", href=True):
                        queue.append((urljoin(url, str(anchor["href"])), depth + 1))

                digest = hashlib.sha256(response.text.encode()).hexdigest()
                if hashes.get(url) == digest:
                    continue
                hashes[url] = digest
                yield RawContent(
                    identifier=url,
                    content=response.text,
                    content_type="html" if is_html else "markdown",
                    url=url,
                )
        self.checkpoint["hashes"] = hashes

    async def health(self) -> tuple[bool, str]:
        """Healthy when the start URL responds."""
        try:
            start = self._start_url
        except ConnectorError as exc:
            return False, exc.message
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                response = await client.get(start)
            return response.status_code < 500, f"HTTP {response.status_code} from {start}"
        except httpx.HTTPError as exc:
            return False, f"cannot reach {start}: {exc}"
