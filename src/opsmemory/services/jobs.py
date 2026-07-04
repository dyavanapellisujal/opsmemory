"""Background ingestion jobs (PRD Long-Running Operations)."""

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from opsmemory.core.errors import NotFoundError
from opsmemory.core.logging import get_logger
from opsmemory.db.models import IngestionJob
from opsmemory.domain.enums import JobStatus
from opsmemory.services.ingestion import IngestionService

logger = get_logger(__name__)


class JobService:
    """Creates ingestion jobs and runs them as background tasks."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        ingestion: IngestionService,
    ) -> None:
        self._session_factory = session_factory
        self._ingestion = ingestion
        self._tasks: set[asyncio.Task[None]] = set()

    async def start(self, connector_id: uuid.UUID) -> uuid.UUID:
        """Create a job row and launch ingestion in the background."""
        async with self._session_factory() as session:
            job = IngestionJob(connector_id=connector_id, status=JobStatus.PENDING)
            session.add(job)
            await session.commit()
            job_id = job.id
        task = asyncio.create_task(self._run(job_id, connector_id))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return job_id

    async def run_and_wait(self, connector_id: uuid.UUID) -> uuid.UUID:
        """Create a job and run it to completion (used by tests and CLI waits)."""
        async with self._session_factory() as session:
            job = IngestionJob(connector_id=connector_id, status=JobStatus.PENDING)
            session.add(job)
            await session.commit()
            job_id = job.id
        await self._run(job_id, connector_id)
        return job_id

    async def get(self, job_id: uuid.UUID) -> IngestionJob:
        """Fetch a job row.

        Raises:
            NotFoundError: If the job does not exist.
        """
        async with self._session_factory() as session:
            job = (
                await session.execute(select(IngestionJob).where(IngestionJob.id == job_id))
            ).scalar_one_or_none()
            if job is None:
                raise NotFoundError(f"Job {job_id} not found")
            return job

    async def _run(self, job_id: uuid.UUID, connector_id: uuid.UUID) -> None:
        """Execute ingestion and record job lifecycle transitions."""
        await self._update(job_id, status=JobStatus.RUNNING, started_at=_now())
        try:
            stats = await self._ingestion.ingest(connector_id)
            failed = "error" in stats
            await self._update(
                job_id,
                status=JobStatus.FAILED if failed else JobStatus.COMPLETED,
                stats=stats,
                error=str(stats.get("error")) if failed else None,
                finished_at=_now(),
            )
        except Exception as exc:
            logger.exception("Ingestion job %s crashed", job_id)
            await self._update(job_id, status=JobStatus.FAILED, error=str(exc), finished_at=_now())

    async def _update(self, job_id: uuid.UUID, **fields: Any) -> None:
        """Apply field updates to a job row."""
        async with self._session_factory() as session:
            job = (
                await session.execute(select(IngestionJob).where(IngestionJob.id == job_id))
            ).scalar_one()
            for key, value in fields.items():
                setattr(job, key, value)
            await session.commit()


def _now() -> datetime:
    """Naive UTC timestamp for DateTime columns."""
    return datetime.now(UTC).replace(tzinfo=None)
