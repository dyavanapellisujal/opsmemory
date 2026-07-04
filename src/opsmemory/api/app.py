"""FastAPI application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import opsmemory
from opsmemory.agent.chat import ChatService
from opsmemory.ai.factory import build_embedding_provider, build_llm_provider
from opsmemory.api.errors import register_error_handlers
from opsmemory.api.schemas.system import HealthResponse, ReadyResponse
from opsmemory.api.v1.router import router as v1_router
from opsmemory.auth.service import AuthService
from opsmemory.connectors.recall import RecallClient
from opsmemory.core.config import Settings, get_settings
from opsmemory.core.logging import configure_logging, get_logger
from opsmemory.db.session import create_engine, create_session_factory
from opsmemory.graph.kuzu_store import KuzuGraphStore
from opsmemory.incidents.chat import IncidentChatService
from opsmemory.incidents.service import IncidentService
from opsmemory.memory.factory import build_memory_engine
from opsmemory.retrieval.engine import RetrievalEngine
from opsmemory.services.ingestion import IngestionService
from opsmemory.services.jobs import JobService
from opsmemory.services.meetings import MeetingService
from opsmemory.services.notifications import NotificationService
from opsmemory.teaching.service import TeachingService

logger = get_logger(__name__)

_DASHBOARD = Path(__file__).parent.parent / "web" / "index.html"


def wire_services(app: FastAPI, settings: Settings) -> None:
    """Build the platform's service graph onto ``app.state``.

    Split from the lifespan so tests can wire fakes first and reuse the
    same composition logic for the pieces they don't replace.
    """
    session_factory: async_sessionmaker[AsyncSession] = app.state.session_factory
    embeddings = build_embedding_provider(settings)
    llm = build_llm_provider(settings)
    memory_engine = build_memory_engine(settings, session_factory, embeddings)
    graph_store = app.state.graph_store  # created in lifespan (filesystem resource)

    retrieval = RetrievalEngine(session_factory, memory_engine, graph_store, settings)
    teaching = TeachingService(
        session_factory, memory_engine, graph_store, llm, settings.llm_max_tokens
    )
    chat = ChatService(retrieval, teaching, llm, settings.llm_max_tokens)
    ingestion = IngestionService(session_factory, memory_engine, graph_store, teaching)

    app.state.embeddings = embeddings
    app.state.llm = llm
    app.state.memory_engine = memory_engine
    app.state.retrieval_engine = retrieval
    app.state.teaching_service = teaching
    app.state.chat_service = chat
    app.state.ingestion_service = ingestion
    app.state.job_service = JobService(session_factory, ingestion)

    # OpsMemory incident hub, scoped chat, notifications, and authentication.
    incident_service = IncidentService(session_factory, memory_engine, graph_store, teaching)
    notifications = NotificationService(session_factory)
    app.state.incident_service = incident_service
    app.state.notification_service = notifications
    app.state.incident_chat_service = IncidentChatService(
        session_factory, memory_engine, llm, settings.llm_max_tokens
    )
    app.state.auth_service = AuthService(
        session_factory, session_ttl_hours=settings.auth_session_ttl_hours
    )

    recall = (
        RecallClient(
            api_key=settings.recall_api_key,
            region=settings.recall_region,
            bot_name=settings.recall_bot_name,
        )
        if settings.recall_api_key
        else None
    )
    app.state.meeting_service = MeetingService(
        session_factory,
        recall,
        llm,
        memory_engine,
        graph_store,
        teaching,
        incident_service,
        notifications,
        llm_max_tokens=max(settings.llm_max_tokens, 4096),
    )
    logger.info(
        "Providers wired: embeddings=%s llm=%s memory=%s",
        embeddings.name,
        llm.name if llm else "none",
        memory_engine.name,
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the OpsMemory FastAPI application.

    Args:
        settings: Optional settings override (used by tests). Defaults to
            environment-derived settings.

    Returns:
        A fully configured FastAPI application.
    """
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """Create shared resources on startup and dispose them on shutdown."""
        engine = create_engine(settings)
        app.state.engine = engine
        app.state.session_factory = create_session_factory(engine)
        app.state.graph_store = KuzuGraphStore(settings.graph_db_path)
        wire_services(app, settings)
        if settings.auth_enabled and await app.state.auth_service.user_count() == 0:
            await app.state.auth_service.ensure_user(
                settings.auth_bootstrap_email,
                settings.auth_bootstrap_password,
                name="Administrator",
                role="admin",
            )
            logger.info("Seeded bootstrap admin user %s", settings.auth_bootstrap_email)
        logger.info("OpsMemory API started (environment=%s)", settings.environment)
        try:
            yield
        finally:
            await engine.dispose()
            logger.info("OpsMemory API shut down")

    app = FastAPI(
        title="OpsMemory",
        summary="The Operational Memory Layer for Engineering Teams",
        version=opsmemory.__version__,
        lifespan=lifespan,
    )
    app.state.settings = settings

    register_error_handlers(app)
    app.include_router(v1_router)

    @app.get("/health", response_model=HealthResponse, tags=["system"])
    async def health() -> HealthResponse:
        """Liveness probe: the process is up."""
        return HealthResponse(status="ok", version=opsmemory.__version__)

    @app.get("/ready", response_model=ReadyResponse, tags=["system"])
    async def ready(request: Request) -> ReadyResponse:
        """Readiness probe: verifies critical dependencies are reachable."""
        checks: dict[str, str] = {}
        try:
            async with request.app.state.session_factory() as session:
                await session.execute(text("SELECT 1"))
            checks["database"] = "ok"
        except Exception as exc:  # pragma: no cover - exercised via unit test fake
            logger.warning("Readiness check failed: %s", exc)
            checks["database"] = "unavailable"
        status = "ready" if all(v == "ok" for v in checks.values()) else "degraded"
        return ReadyResponse(status=status, checks=checks)

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def dashboard() -> HTMLResponse:
        """Serve the single-page web dashboard."""
        return HTMLResponse(_DASHBOARD.read_text(encoding="utf-8"))

    return app
