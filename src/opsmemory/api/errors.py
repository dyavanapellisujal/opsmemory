"""API error handling: maps platform errors to the standard error envelope."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from opsmemory.api.schemas.common import ErrorDetail, ErrorResponse
from opsmemory.core.errors import OpsMemoryError
from opsmemory.core.logging import get_logger

logger = get_logger(__name__)


def register_error_handlers(app: FastAPI) -> None:
    """Register exception handlers producing the consistent error envelope.

    Every error response follows::

        {"error": {"code": "...", "message": "...", "details": {}}}
    """

    @app.exception_handler(OpsMemoryError)
    async def handle_opsmemory_error(request: Request, exc: OpsMemoryError) -> JSONResponse:
        body = ErrorResponse(
            error=ErrorDetail(code=exc.code, message=exc.message, details=exc.details)
        )
        return JSONResponse(status_code=exc.status_code, content=body.model_dump())

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        body = ErrorResponse(
            error=ErrorDetail(code="INTERNAL_ERROR", message="An internal error occurred.")
        )
        return JSONResponse(status_code=500, content=body.model_dump())
