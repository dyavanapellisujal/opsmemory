"""FastAPI dependency providers (composition root for request-scoped objects).

Long-lived resources (engine, providers, memory/graph engines, services) are
created once in the app lifespan and attached to ``app.state``; tests
substitute any of them by replacing the attribute (ADR-0005).
"""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from opsmemory.agent.chat import ChatService
from opsmemory.auth.service import AuthService
from opsmemory.core.config import Settings
from opsmemory.core.errors import OpsMemoryError
from opsmemory.db.models import User
from opsmemory.graph.store import GraphStore
from opsmemory.incidents.chat import IncidentChatService
from opsmemory.incidents.service import IncidentService
from opsmemory.memory.base import MemoryEngine
from opsmemory.retrieval.engine import RetrievalEngine
from opsmemory.services.jobs import JobService
from opsmemory.services.meetings import MeetingService
from opsmemory.services.notifications import NotificationService
from opsmemory.services.stats import StatsService
from opsmemory.teaching.service import TeachingService


class UnauthorizedError(OpsMemoryError):
    """Raised when a protected route is accessed without a valid session."""

    code = "UNAUTHORIZED"
    status_code = 401


def get_settings_dep(request: Request) -> Settings:
    """Return the application settings attached to the app."""
    settings: Settings = request.app.state.settings
    return settings


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield a request-scoped database session."""
    factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    async with factory() as session:
        yield session


def get_memory_engine(request: Request) -> MemoryEngine:
    """Return the process-wide memory engine."""
    engine: MemoryEngine = request.app.state.memory_engine
    return engine


def get_graph_store(request: Request) -> GraphStore:
    """Return the process-wide graph store."""
    store: GraphStore = request.app.state.graph_store
    return store


def get_retrieval_engine(request: Request) -> RetrievalEngine:
    """Return the hybrid retrieval engine."""
    engine: RetrievalEngine = request.app.state.retrieval_engine
    return engine


def get_chat_service(request: Request) -> ChatService:
    """Return the chat (AI agent) service."""
    service: ChatService = request.app.state.chat_service
    return service


def get_teaching_service(request: Request) -> TeachingService:
    """Return the teaching pipeline service."""
    service: TeachingService = request.app.state.teaching_service
    return service


def get_job_service(request: Request) -> JobService:
    """Return the background job service."""
    service: JobService = request.app.state.job_service
    return service


def get_meeting_service(request: Request) -> MeetingService:
    """Return the meeting connector service."""
    service: MeetingService = request.app.state.meeting_service
    return service


def get_incident_service(request: Request) -> IncidentService:
    """Return the incident hub service."""
    service: IncidentService = request.app.state.incident_service
    return service


def get_incident_chat_service(request: Request) -> IncidentChatService:
    """Return the incident-scoped chat service."""
    service: IncidentChatService = request.app.state.incident_chat_service
    return service


def get_auth_service(request: Request) -> AuthService:
    """Return the authentication service."""
    service: AuthService = request.app.state.auth_service
    return service


def get_notification_service(request: Request) -> NotificationService:
    """Return the notification service."""
    service: NotificationService = request.app.state.notification_service
    return service


async def get_current_user(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> User | None:
    """Resolve the current user from a bearer token.

    Returns ``None`` when auth is disabled (tests/dev) so protected routes
    stay open; otherwise a missing/invalid token raises 401.
    """
    settings: Settings = request.app.state.settings
    if not settings.auth_enabled:
        return None
    token = ""
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    if not token:
        raise UnauthorizedError("Authentication required")
    auth: AuthService = request.app.state.auth_service
    user = await auth.authenticate_token(token)
    if user is None:
        raise UnauthorizedError("Invalid or expired session")
    return user


SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
MemoryEngineDep = Annotated[MemoryEngine, Depends(get_memory_engine)]
GraphStoreDep = Annotated[GraphStore, Depends(get_graph_store)]
RetrievalEngineDep = Annotated[RetrievalEngine, Depends(get_retrieval_engine)]
ChatServiceDep = Annotated[ChatService, Depends(get_chat_service)]
TeachingServiceDep = Annotated[TeachingService, Depends(get_teaching_service)]
JobServiceDep = Annotated[JobService, Depends(get_job_service)]
MeetingServiceDep = Annotated[MeetingService, Depends(get_meeting_service)]
IncidentServiceDep = Annotated[IncidentService, Depends(get_incident_service)]
IncidentChatServiceDep = Annotated[IncidentChatService, Depends(get_incident_chat_service)]
AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
NotificationServiceDep = Annotated[NotificationService, Depends(get_notification_service)]
CurrentUserDep = Annotated[User | None, Depends(get_current_user)]


def get_stats_service(session: SessionDep) -> StatsService:
    """Build the statistics service for the current request."""
    return StatsService(session)


StatsServiceDep = Annotated[StatsService, Depends(get_stats_service)]
