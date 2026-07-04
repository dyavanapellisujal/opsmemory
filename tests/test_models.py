"""Tests for ORM models and their relationships."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from opsmemory.db.models import (
    Connector,
    Document,
    Incident,
    IngestionJob,
    OperationalExperience,
    Repository,
    Service,
    Team,
)
from opsmemory.domain.enums import (
    ConnectorType,
    DocumentSource,
    IncidentSeverity,
    IncidentStatus,
    JobStatus,
)


async def test_team_owns_service_and_repository(session: AsyncSession) -> None:
    team = Team(name="platform", description="Platform Engineering")
    repo = Repository(name="payments-api", provider="github", owner_team=team)
    service = Service(name="payments-api", owner_team=team, repository=repo)
    session.add_all([team, repo, service])
    await session.commit()

    loaded = (
        await session.execute(select(Service).where(Service.name == "payments-api"))
    ).scalar_one()
    assert loaded.owner_team is not None and loaded.owner_team.name == "platform"
    assert loaded.repository is not None and loaded.repository.provider == "github"
    assert isinstance(loaded.id, uuid.UUID)


async def test_service_dependencies(session: AsyncSession) -> None:
    redis = Service(name="redis")
    payments = Service(name="payments-api", dependencies=[redis])
    session.add_all([redis, payments])
    await session.commit()

    loaded = (
        await session.execute(select(Service).where(Service.name == "payments-api"))
    ).scalar_one()
    assert [dep.name for dep in loaded.dependencies] == ["redis"]


async def test_incident_with_experience(session: AsyncSession) -> None:
    incident = Incident(
        title="Redis outage",
        severity=IncidentSeverity.SEV1,
        status=IncidentStatus.RESOLVED,
        root_cause="Expired credentials",
    )
    experience = OperationalExperience(
        problem="Redis authentication failure",
        root_cause="Expired credentials",
        resolution="Rotate Kubernetes Secret and restart the Deployment",
        lessons_learned="Rotate credentials before expiration",
        confidence=0.8,
        incident=incident,
    )
    session.add_all([incident, experience])
    await session.commit()

    loaded = (
        await session.execute(
            select(OperationalExperience).where(
                OperationalExperience.problem == "Redis authentication failure"
            )
        )
    ).scalar_one()
    assert loaded.incident is not None and loaded.incident.title == "Redis outage"
    assert loaded.confidence == 0.8


async def test_connector_document_and_job(session: AsyncSession) -> None:
    connector = Connector(
        name="local-docs",
        type=ConnectorType.LOCAL_FILES,
        config={"path": "./docs"},
        checkpoint={"last_run": None},
    )
    document = Document(
        title="Deployment Runbook",
        source=DocumentSource.LOCAL_FILES,
        content="# Deploying payments-api",
        content_hash="abc123",
        tags=["runbook", "payments"],
        connector=connector,
    )
    job = IngestionJob(connector=connector, status=JobStatus.COMPLETED, stats={"documents": 1})
    session.add_all([connector, document, job])
    await session.commit()

    loaded = (
        await session.execute(select(Connector).where(Connector.name == "local-docs"))
    ).scalar_one()
    assert loaded.type is ConnectorType.LOCAL_FILES
    assert [d.title for d in loaded.documents] == ["Deployment Runbook"]
    assert loaded.jobs[0].status is JobStatus.COMPLETED
    assert loaded.documents[0].tags == ["runbook", "payments"]
