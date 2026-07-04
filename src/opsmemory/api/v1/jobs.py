"""Ingestion job endpoints."""

import uuid

from fastapi import APIRouter
from sqlalchemy import select

from opsmemory.api.dependencies import JobServiceDep, SessionDep
from opsmemory.api.schemas.knowledge import JobOut
from opsmemory.db.models import IngestionJob

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=list[JobOut])
async def list_jobs(session: SessionDep) -> list[IngestionJob]:
    """List ingestion jobs, newest first."""
    return list(
        (
            await session.execute(
                select(IngestionJob).order_by(IngestionJob.created_at.desc()).limit(50)
            )
        )
        .scalars()
        .all()
    )


@router.get("/{job_id}", response_model=JobOut)
async def get_job(job_id: uuid.UUID, jobs: JobServiceDep) -> IngestionJob:
    """Return one ingestion job with its status and statistics."""
    return await jobs.get(job_id)
