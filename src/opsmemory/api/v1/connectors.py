"""Connector management endpoints."""

import uuid

from fastapi import APIRouter, status
from sqlalchemy import select

from opsmemory.api.dependencies import JobServiceDep, SessionDep
from opsmemory.api.schemas.knowledge import (
    ConnectorCreate,
    ConnectorHealthOut,
    ConnectorOut,
    SyncAccepted,
)
from opsmemory.connectors.registry import build_connector
from opsmemory.core.errors import NotFoundError, ValidationFailedError
from opsmemory.db.models import Connector
from opsmemory.domain.enums import JobStatus

router = APIRouter(prefix="/connectors", tags=["connectors"])


async def _get_connector(session: SessionDep, connector_id: uuid.UUID) -> Connector:
    """Load a connector row or raise 404."""
    connector = (
        await session.execute(select(Connector).where(Connector.id == connector_id))
    ).scalar_one_or_none()
    if connector is None:
        raise NotFoundError(f"Connector {connector_id} not found", code="CONNECTOR_NOT_FOUND")
    return connector


@router.get("", response_model=list[ConnectorOut])
async def list_connectors(session: SessionDep) -> list[Connector]:
    """List all configured connectors."""
    return list((await session.execute(select(Connector))).scalars().all())


@router.post("", response_model=ConnectorOut, status_code=status.HTTP_201_CREATED)
async def register_connector(payload: ConnectorCreate, session: SessionDep) -> Connector:
    """Register a new knowledge source."""
    existing = (
        await session.execute(select(Connector).where(Connector.name == payload.name))
    ).scalar_one_or_none()
    if existing is not None:
        raise ValidationFailedError(
            f"A connector named {payload.name!r} already exists", code="CONNECTOR_EXISTS"
        )
    # Validate config eagerly so bad connectors fail at registration time.
    implementation = build_connector(payload.type, payload.config, {})
    healthy, message = await implementation.health()
    connector = Connector(name=payload.name, type=payload.type, config=payload.config)
    if not healthy:
        raise ValidationFailedError(
            f"Connector configuration is not usable: {message}",
            code="CONNECTOR_UNHEALTHY",
        )
    session.add(connector)
    await session.commit()
    return connector


@router.get("/{connector_id}", response_model=ConnectorOut)
async def connector_details(connector_id: uuid.UUID, session: SessionDep) -> Connector:
    """Return connector configuration and synchronization status."""
    return await _get_connector(session, connector_id)


@router.delete("/{connector_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_connector(connector_id: uuid.UUID, session: SessionDep) -> None:
    """Remove a connector (its ingested documents remain)."""
    connector = await _get_connector(session, connector_id)
    await session.delete(connector)
    await session.commit()


@router.post("/{connector_id}/sync", response_model=SyncAccepted, status_code=202)
async def sync_connector(
    connector_id: uuid.UUID, session: SessionDep, jobs: JobServiceDep
) -> SyncAccepted:
    """Trigger an asynchronous ingestion job for this connector."""
    await _get_connector(session, connector_id)
    job_id = await jobs.start(connector_id)
    return SyncAccepted(job_id=job_id, status=JobStatus.PENDING)


@router.get("/{connector_id}/health", response_model=ConnectorHealthOut)
async def connector_health(connector_id: uuid.UUID, session: SessionDep) -> ConnectorHealthOut:
    """Check that the connector's source system is reachable."""
    connector = await _get_connector(session, connector_id)
    implementation = build_connector(connector.type, connector.config, connector.checkpoint)
    healthy, message = await implementation.health()
    return ConnectorHealthOut(healthy=healthy, message=message)
