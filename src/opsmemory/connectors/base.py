"""Connector interface.

Every knowledge source implements this small contract; the ingestion
pipeline, memory layer, retrieval engine, and AI agent never know where a
document came from. Adding a new source (GitHub, Confluence, Slack, ...)
means implementing this interface and registering it — nothing else changes.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any

from opsmemory.domain.enums import ConnectorType, DocumentSource
from opsmemory.processing.models import RawContent


class BaseConnector(ABC):
    """Contract every knowledge-source connector implements.

    Connectors are read-only, incremental, and idempotent: ``discover``
    yields raw content, and the ``checkpoint`` mapping (persisted by the
    platform between runs) lets a connector skip content that has not
    changed since the previous synchronization.
    """

    type: ConnectorType
    source: DocumentSource

    def __init__(self, config: dict[str, Any], checkpoint: dict[str, Any]) -> None:
        self.config = config
        self.checkpoint = dict(checkpoint)

    @abstractmethod
    def discover(self) -> AsyncIterator[RawContent]:
        """Yield raw content for every new or modified resource.

        Implementations should consult ``self.checkpoint`` to skip
        unchanged resources and update it as resources are yielded.
        """

    @abstractmethod
    async def health(self) -> tuple[bool, str]:
        """Check that the source is reachable.

        Returns:
            ``(healthy, message)``.
        """

    def metadata(self) -> dict[str, Any]:
        """Describe this connector instance for APIs and dashboards."""
        return {"type": self.type.value, "config": self.config}
