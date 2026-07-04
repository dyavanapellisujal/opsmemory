"""OpsMemory MCP server.

Exposes organizational memory to MCP clients (Claude Code, IDEs, agents) as
tools over stdio. The server is a thin client of the OpsMemory REST API, so
it can run anywhere the API is reachable.

Usage:
    opsmemory-mcp                          # stdio transport
    OPSMEMORY_API_URL=http://host:8000 opsmemory-mcp

Claude Code registration:
    claude mcp add opsmemory -- opsmemory-mcp
"""

from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

from opsmemory.core.config import get_settings

mcp = FastMCP(
    "opsmemory",
    instructions=(
        "OpsMemory is the engineering organization's operational memory. "
        "Use `ask` for evidence-backed answers, `search` for raw evidence, "
        "`teach` to store operational lessons, and the graph/entity tools "
        "to explore services, dependencies, and ownership."
    ),
)


def _base_url() -> str:
    """Base URL of the OpsMemory API."""
    return get_settings().api_url.rstrip("/")


async def _get(path: str) -> Any:
    """GET a path from the OpsMemory API."""
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.get(f"{_base_url()}{path}")
        response.raise_for_status()
        return response.json()


async def _post(path: str, payload: dict[str, Any]) -> Any:
    """POST JSON to the OpsMemory API."""
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(f"{_base_url()}{path}", json=payload)
        response.raise_for_status()
        return response.json()


@mcp.tool()
async def ask(question: str) -> dict[str, Any]:
    """Ask the organization's operational memory a question.

    Returns an evidence-backed answer with citations and a confidence score.
    Use for: incident investigation, deployment procedures, ownership,
    architecture rationale, "have we seen this before".
    """
    result: dict[str, Any] = await _post("/api/v1/chat", {"message": question})
    return result


@mcp.tool()
async def search(query: str) -> dict[str, Any]:
    """Hybrid search over organizational knowledge without LLM synthesis.

    Returns raw evidence: semantic memories, documents, operational
    experiences, services, and graph relationships.
    """
    result: dict[str, Any] = await _post("/api/v1/search", {"query": query})
    return result


@mcp.tool()
async def teach(lesson: str, author: str = "mcp") -> dict[str, Any]:
    """Teach OpsMemory an operational lesson so future answers improve.

    Describe the problem, root cause, resolution, and lesson learned in
    plain text; the platform extracts and stores a structured experience.
    """
    result: dict[str, Any] = await _post(
        "/api/v1/experiences", {"content": lesson, "author": author}
    )
    return result


@mcp.tool()
async def list_services() -> list[dict[str, Any]]:
    """List all services known to the platform with their owners."""
    result: list[dict[str, Any]] = await _get("/api/v1/services")
    return result


@mcp.tool()
async def graph_neighbors(entity: str, depth: int = 2) -> dict[str, Any]:
    """Explore knowledge-graph relationships around an entity (service, doc, technology)."""
    result: dict[str, Any] = await _get(f"/api/v1/graph/{entity}?depth={depth}")
    return result


@mcp.tool()
async def service_dependencies(service: str, depth: int = 3) -> dict[str, Any]:
    """Return the transitive dependency graph of a service."""
    result: dict[str, Any] = await _get(
        f"/api/v1/graph/services/{service}/dependencies?depth={depth}"
    )
    return result


@mcp.tool()
async def platform_stats() -> dict[str, Any]:
    """Return knowledge statistics: documents, memories, experiences, graph size."""
    result: dict[str, Any] = await _get("/api/v1/stats")
    return result


def main() -> None:
    """Run the MCP server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
