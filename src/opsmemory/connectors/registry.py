"""Connector registry: maps connector types to implementations.

New connectors (GitHub, Confluence, Slack, ...) plug in by adding one entry
here — the ingestion pipeline and APIs are already generic.
"""

from typing import Any

from opsmemory.connectors.base import BaseConnector
from opsmemory.connectors.http import HttpDocsConnector
from opsmemory.connectors.local import LocalFilesConnector
from opsmemory.core.errors import ConnectorError
from opsmemory.domain.enums import ConnectorType

_REGISTRY: dict[ConnectorType, type[BaseConnector]] = {
    ConnectorType.LOCAL_FILES: LocalFilesConnector,
    ConnectorType.HTTP_DOCS: HttpDocsConnector,
}


def build_connector(
    connector_type: ConnectorType,
    config: dict[str, Any],
    checkpoint: dict[str, Any],
) -> BaseConnector:
    """Instantiate the connector implementation for a stored connector row.

    Raises:
        ConnectorError: If the type has no registered implementation
            (e.g. ``github``, which is planned but not yet shipped).
    """
    implementation = _REGISTRY.get(connector_type)
    if implementation is None:
        raise ConnectorError(
            f"No implementation registered for connector type {connector_type.value!r}. "
            f"Available: {sorted(t.value for t in _REGISTRY)}"
        )
    return implementation(config=config, checkpoint=checkpoint)


def available_types() -> list[str]:
    """Names of connector types that can be instantiated."""
    return sorted(t.value for t in _REGISTRY)
