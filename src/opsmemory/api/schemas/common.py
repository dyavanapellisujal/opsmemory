"""Common API schemas shared across all endpoints."""

from typing import Any

from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    """Machine-readable description of an API error."""

    code: str = Field(description="Stable error code, e.g. DOCUMENT_NOT_FOUND.")
    message: str = Field(description="Human-readable error description.")
    details: dict[str, Any] = Field(default_factory=dict, description="Structured context.")


class ErrorResponse(BaseModel):
    """Envelope for all API error responses."""

    error: ErrorDetail
