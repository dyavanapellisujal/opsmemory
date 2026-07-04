"""Platform error types.

All errors raised by OpsMemory services derive from :class:`OpsMemoryError`
and carry a stable machine-readable ``code`` so API responses and CLI exit
codes remain consistent across the platform.
"""

from typing import Any


class OpsMemoryError(Exception):
    """Base class for all OpsMemory errors.

    Attributes:
        code: Stable machine-readable error code (e.g. ``DOCUMENT_NOT_FOUND``).
        message: Human-readable description of the failure.
        status_code: HTTP status the API layer should respond with.
        details: Optional structured context about the failure.
    """

    code: str = "INTERNAL_ERROR"
    status_code: int = 500

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code
        self.details: dict[str, Any] = details or {}


class NotFoundError(OpsMemoryError):
    """Raised when a requested resource does not exist."""

    code = "NOT_FOUND"
    status_code = 404


class ValidationFailedError(OpsMemoryError):
    """Raised when a request or payload fails domain validation."""

    code = "VALIDATION_FAILED"
    status_code = 422


class ConnectorError(OpsMemoryError):
    """Raised when a connector fails to communicate with its source system."""

    code = "CONNECTOR_ERROR"
    status_code = 502


class StorageError(OpsMemoryError):
    """Raised when a storage backend is unavailable or misbehaving."""

    code = "STORAGE_ERROR"
    status_code = 503
