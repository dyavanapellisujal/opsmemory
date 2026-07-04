"""Notification service: durable lifecycle notifications polled by the web app."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from opsmemory.core.logging import get_logger
from opsmemory.db.models import Notification

logger = get_logger(__name__)


class NotificationService:
    """Creates and lists user notifications (Meeting Intelligence lifecycle)."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def notify(
        self,
        kind: str,
        title: str,
        *,
        body: str | None = None,
        incident_id: uuid.UUID | None = None,
    ) -> None:
        """Record a notification."""
        async with self._session_factory() as session:
            session.add(Notification(kind=kind, title=title, body=body, incident_id=incident_id))
            await session.commit()
        logger.info("Notification kind=%s title=%s", kind, title)

    async def list(self, *, limit: int = 30, unread_only: bool = False) -> list[Notification]:
        """List recent notifications, newest first."""
        async with self._session_factory() as session:
            stmt = select(Notification).order_by(Notification.created_at.desc()).limit(limit)
            if unread_only:
                stmt = stmt.where(Notification.read.is_(False))
            return list((await session.execute(stmt)).scalars().all())

    async def mark_all_read(self) -> int:
        """Mark every notification read; returns how many changed."""
        async with self._session_factory() as session:
            rows = (
                (await session.execute(select(Notification).where(Notification.read.is_(False))))
                .scalars()
                .all()
            )
            for row in rows:
                row.read = True
            await session.commit()
            return len(rows)
