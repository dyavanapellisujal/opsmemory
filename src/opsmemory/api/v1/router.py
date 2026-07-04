"""Aggregated router for API v1."""

from fastapi import APIRouter

from opsmemory.api.v1 import (
    auth,
    chat,
    connectors,
    dashboard,
    documents,
    entities,
    experiences,
    graph,
    incidents,
    jobs,
    meetings,
    notifications,
    search,
    system,
    webhooks,
)

router = APIRouter(prefix="/api/v1")
router.include_router(auth.router)
router.include_router(dashboard.router)
router.include_router(incidents.router)
router.include_router(system.router)
router.include_router(connectors.router)
router.include_router(documents.router)
router.include_router(search.router)
router.include_router(chat.router)
router.include_router(experiences.router)
router.include_router(entities.router)
router.include_router(graph.router)
router.include_router(jobs.router)
router.include_router(meetings.router)
router.include_router(notifications.router)
router.include_router(webhooks.router)
