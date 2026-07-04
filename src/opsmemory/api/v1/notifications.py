"""Notification endpoints (polled by the web app)."""

from fastapi import APIRouter, Query

from opsmemory.api.dependencies import CurrentUserDep, NotificationServiceDep
from opsmemory.api.schemas.notifications import NotificationOut
from opsmemory.db.models import Notification

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationOut])
async def list_notifications(
    service: NotificationServiceDep,
    user: CurrentUserDep,
    unread_only: bool = Query(default=False),
) -> list[Notification]:
    """List recent notifications, newest first."""
    return await service.list(unread_only=unread_only)


@router.post("/read")
async def mark_all_read(service: NotificationServiceDep, user: CurrentUserDep) -> dict[str, int]:
    """Mark all notifications as read."""
    return {"updated": await service.mark_all_read()}
