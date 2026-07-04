"""Chat endpoint: the AI agent (retrieve → reason → cite)."""

from fastapi import APIRouter

from opsmemory.agent.chat import ChatResponse
from opsmemory.api.dependencies import ChatServiceDep
from opsmemory.api.schemas.knowledge import ChatRequest

router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, service: ChatServiceDep) -> ChatResponse:
    """Answer an engineering question (or learn from a teaching message)."""
    return await service.chat(payload.message, author=payload.author)
