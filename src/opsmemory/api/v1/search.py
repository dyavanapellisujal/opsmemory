"""Hybrid search endpoint: evidence retrieval without LLM reasoning."""

from fastapi import APIRouter

from opsmemory.api.dependencies import RetrievalEngineDep
from opsmemory.api.schemas.knowledge import SearchRequest, SearchResponse

router = APIRouter(tags=["search"])


@router.post("/search", response_model=SearchResponse)
async def search(payload: SearchRequest, retrieval: RetrievalEngineDep) -> SearchResponse:
    """Run hybrid retrieval and return the ranked evidence package."""
    package = await retrieval.retrieve(payload.query)
    return SearchResponse(
        query=package.query,
        intent=package.intent,
        memories=package.memories,
        documents=package.documents,
        experiences=package.experiences,
        services=package.services,
        graph_facts=package.graph_facts,
    )
