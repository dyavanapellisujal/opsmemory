"""Knowledge graph exploration endpoints."""

from fastapi import APIRouter, Query

from opsmemory.api.dependencies import GraphStoreDep
from opsmemory.api.schemas.knowledge import GraphNeighborsOut

router = APIRouter(prefix="/graph", tags=["graph"])


@router.get("/{entity_name}", response_model=GraphNeighborsOut)
async def related_entities(
    entity_name: str,
    graph: GraphStoreDep,
    depth: int = Query(default=1, ge=1, le=5),
) -> GraphNeighborsOut:
    """Return edges around an entity in the knowledge graph."""
    edges = await graph.neighbors(entity_name, depth=depth)
    return GraphNeighborsOut(entity=entity_name.lower(), edges=edges)


@router.get("/services/{service_name}/dependencies", response_model=GraphNeighborsOut)
async def service_dependencies(
    service_name: str,
    graph: GraphStoreDep,
    depth: int = Query(default=3, ge=1, le=5),
) -> GraphNeighborsOut:
    """Return the transitive dependency graph for a service."""
    edges = await graph.dependencies(service_name, depth=depth)
    return GraphNeighborsOut(entity=service_name.lower(), edges=edges)
