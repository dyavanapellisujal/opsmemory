"""HTTP client the CLI uses to communicate with the OpsMemory API."""

import json
from typing import Any

import httpx

from opsmemory.core.config import Settings
from opsmemory.core.errors import OpsMemoryError


class APIClientError(OpsMemoryError):
    """Raised when the CLI cannot reach or gets an error from the API."""

    code = "API_CLIENT_ERROR"


def _api_error_detail(body: str) -> str:
    """Extract the API's error message from a response body, if present."""
    try:
        error = json.loads(body).get("error", {})
        message = error.get("message")
        return f": {message}" if message else ""
    except (json.JSONDecodeError, AttributeError):
        return ""


class APIClient:
    """Thin synchronous client for the OpsMemory REST API.

    The CLI is a short-lived process, so a synchronous client keeps the
    command implementations simple while the server remains fully async.
    """

    def __init__(self, settings: Settings, timeout: float = 30.0) -> None:
        self._base_url = settings.api_url.rstrip("/")
        self._timeout = timeout

    def _request(self, method: str, path: str, json: Any | None = None) -> Any:
        """Perform a request and return the decoded JSON body.

        Raises:
            APIClientError: If the API is unreachable or returns an error.
        """
        try:
            response = httpx.request(
                method, f"{self._base_url}{path}", json=json, timeout=self._timeout
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise APIClientError(
                f"API returned {exc.response.status_code} for {path}"
                + _api_error_detail(exc.response.text),
                details={"status_code": exc.response.status_code, "body": exc.response.text},
            ) from exc
        except httpx.HTTPError as exc:
            raise APIClientError(f"Cannot reach OpsMemory API at {self._base_url}: {exc}") from exc
        if response.status_code == 204 or not response.content:
            return {}
        return response.json()

    def get(self, path: str) -> Any:
        """GET a path and return the decoded JSON body."""
        return self._request("GET", path)

    def post(self, path: str, json: Any | None = None) -> Any:
        """POST a JSON body and return the decoded response."""
        return self._request("POST", path, json=json)

    def delete(self, path: str) -> Any:
        """DELETE a path."""
        return self._request("DELETE", path)
