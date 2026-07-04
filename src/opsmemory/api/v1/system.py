"""System endpoints: platform statistics."""

from fastapi import APIRouter

from opsmemory.api.dependencies import GraphStoreDep, StatsServiceDep
from opsmemory.api.schemas.system import StatsResponse

router = APIRouter(tags=["system"])


@router.get("/stats", response_model=StatsResponse)
async def get_stats(stats: StatsServiceDep, graph: GraphStoreDep) -> StatsResponse:
    """Return platform-wide knowledge statistics."""
    counts = await stats.collect()
    counts.update(await graph.stats())
    return StatsResponse(**counts)
