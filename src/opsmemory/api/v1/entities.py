"""Entity endpoints: services, teams, incidents, repositories."""

import uuid

from fastapi import APIRouter
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from opsmemory.api.dependencies import SessionDep
from opsmemory.api.schemas.knowledge import (
    RepositoryOut,
    ServiceOut,
    TeamOut,
)
from opsmemory.core.errors import NotFoundError
from opsmemory.db.models import Repository, Service, Team

router = APIRouter(tags=["entities"])


def _service_out(service: Service) -> ServiceOut:
    """Map a Service row (with loaded owner) to its schema."""
    return ServiceOut(
        id=service.id,
        name=service.name,
        description=service.description,
        environment=service.environment,
        namespace=service.namespace,
        owner_team=service.owner_team.name if service.owner_team else None,
    )


@router.get("/services", response_model=list[ServiceOut])
async def list_services(session: SessionDep) -> list[ServiceOut]:
    """List all known services."""
    rows = (
        (await session.execute(select(Service).options(selectinload(Service.owner_team))))
        .scalars()
        .all()
    )
    return [_service_out(s) for s in rows]


@router.get("/services/{service_id}", response_model=ServiceOut)
async def get_service(service_id: uuid.UUID, session: SessionDep) -> ServiceOut:
    """Return one service with ownership metadata."""
    service = (
        await session.execute(
            select(Service)
            .where(Service.id == service_id)
            .options(selectinload(Service.owner_team))
        )
    ).scalar_one_or_none()
    if service is None:
        raise NotFoundError(f"Service {service_id} not found", code="SERVICE_NOT_FOUND")
    return _service_out(service)


@router.get("/teams", response_model=list[TeamOut])
async def list_teams(session: SessionDep) -> list[Team]:
    """List all teams."""
    return list((await session.execute(select(Team))).scalars().all())


@router.get("/repositories", response_model=list[RepositoryOut])
async def list_repositories(session: SessionDep) -> list[Repository]:
    """List repositories."""
    return list((await session.execute(select(Repository))).scalars().all())
