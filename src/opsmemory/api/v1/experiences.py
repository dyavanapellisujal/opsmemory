"""Operational experience endpoints, including teaching."""

import uuid

from fastapi import APIRouter, status
from sqlalchemy import select

from opsmemory.api.dependencies import SessionDep, TeachingServiceDep
from opsmemory.api.schemas.knowledge import ExperienceOut, TeachRequest
from opsmemory.core.errors import NotFoundError
from opsmemory.db.models import OperationalExperience
from opsmemory.teaching.service import TeachingResult

router = APIRouter(prefix="/experiences", tags=["experiences"])


@router.get("", response_model=list[ExperienceOut])
async def list_experiences(session: SessionDep) -> list[OperationalExperience]:
    """List learned operational experiences, most confident first."""
    return list(
        (
            await session.execute(
                select(OperationalExperience).order_by(OperationalExperience.confidence.desc())
            )
        )
        .scalars()
        .all()
    )


@router.post("", response_model=TeachingResult, status_code=status.HTTP_201_CREATED)
async def teach(payload: TeachRequest, teaching: TeachingServiceDep) -> TeachingResult:
    """Teach OpsMemory a new operational experience."""
    return await teaching.teach(payload.content, author=payload.author)


@router.get("/{experience_id}", response_model=ExperienceOut)
async def get_experience(experience_id: uuid.UUID, session: SessionDep) -> OperationalExperience:
    """Return one operational experience."""
    experience = (
        await session.execute(
            select(OperationalExperience).where(OperationalExperience.id == experience_id)
        )
    ).scalar_one_or_none()
    if experience is None:
        raise NotFoundError(f"Experience {experience_id} not found", code="EXPERIENCE_NOT_FOUND")
    return experience
