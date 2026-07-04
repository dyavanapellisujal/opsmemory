"""initial schema.

Revision ID: d2081a9dbf78
Revises:
Create Date: 2026-07-03 00:46:58.171035
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from opsmemory.db.types import GUID

revision: str = "d2081a9dbf78"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply the migration."""
    # pgvector powers semantic retrieval from Milestone 3 onward; enabling it
    # here keeps every environment vector-ready from the first migration.
    if op.get_bind().dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "connectors",
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column(
            "type",
            sa.Enum(
                "local_files",
                "github",
                "http_docs",
                name="connectortype",
                native_enum=False,
                length=30,
            ),
            nullable=False,
        ),
        sa.Column(
            "config",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "active", "disabled", "error", name="connectorstatus", native_enum=False, length=30
            ),
            nullable=False,
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column(
            "checkpoint",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("last_sync_at", sa.DateTime(), nullable=True),
        sa.Column("id", GUID(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_connectors")),
    )
    op.create_index(op.f("ix_connectors_name"), "connectors", ["name"], unique=True)
    op.create_index(op.f("ix_connectors_type"), "connectors", ["type"], unique=False)
    op.create_table(
        "teams",
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("slack_channel", sa.String(length=200), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column(
            "responsibilities",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("id", GUID(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_teams")),
    )
    op.create_index(op.f("ix_teams_name"), "teams", ["name"], unique=True)
    op.create_table(
        "incidents",
        sa.Column("external_id", sa.String(length=100), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "severity",
            sa.Enum(
                "sev1",
                "sev2",
                "sev3",
                "sev4",
                name="incidentseverity",
                native_enum=False,
                length=30,
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "open", "mitigated", "resolved", name="incidentstatus", native_enum=False, length=30
            ),
            nullable=False,
        ),
        sa.Column("root_cause", sa.Text(), nullable=True),
        sa.Column("resolution", sa.Text(), nullable=True),
        sa.Column("lessons_learned", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.Column("team_id", GUID(length=36), nullable=True),
        sa.Column("id", GUID(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], name=op.f("fk_incidents_team_id_teams")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_incidents")),
    )
    op.create_index(op.f("ix_incidents_external_id"), "incidents", ["external_id"], unique=True)
    op.create_index(op.f("ix_incidents_severity"), "incidents", ["severity"], unique=False)
    op.create_index(op.f("ix_incidents_status"), "incidents", ["status"], unique=False)
    op.create_index(op.f("ix_incidents_title"), "incidents", ["title"], unique=False)
    op.create_table(
        "ingestion_jobs",
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "running",
                "completed",
                "failed",
                name="jobstatus",
                native_enum=False,
                length=30,
            ),
            nullable=False,
        ),
        sa.Column(
            "stats",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("connector_id", GUID(length=36), nullable=False),
        sa.Column("id", GUID(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["connector_id"],
            ["connectors.id"],
            name=op.f("fk_ingestion_jobs_connector_id_connectors"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ingestion_jobs")),
    )
    op.create_index(op.f("ix_ingestion_jobs_status"), "ingestion_jobs", ["status"], unique=False)
    op.create_table(
        "repositories",
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=True),
        sa.Column("url", sa.String(length=2000), nullable=True),
        sa.Column("default_branch", sa.String(length=200), nullable=True),
        sa.Column("language", sa.String(length=100), nullable=True),
        sa.Column("visibility", sa.String(length=20), nullable=True),
        sa.Column(
            "topics",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("owner_team_id", GUID(length=36), nullable=True),
        sa.Column("id", GUID(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["owner_team_id"], ["teams.id"], name=op.f("fk_repositories_owner_team_id_teams")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_repositories")),
        sa.UniqueConstraint("url", name=op.f("uq_repositories_url")),
    )
    op.create_index(op.f("ix_repositories_name"), "repositories", ["name"], unique=False)
    op.create_table(
        "documents",
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "source",
            sa.Enum(
                "local_files",
                "github",
                "http_docs",
                "user",
                name="documentsource",
                native_enum=False,
                length=30,
            ),
            nullable=False,
        ),
        sa.Column("url", sa.String(length=2000), nullable=True),
        sa.Column("author", sa.String(length=200), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "tags",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "extra",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("last_modified", sa.DateTime(), nullable=True),
        sa.Column("repository_id", GUID(length=36), nullable=True),
        sa.Column("connector_id", GUID(length=36), nullable=True),
        sa.Column("id", GUID(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["connector_id"], ["connectors.id"], name=op.f("fk_documents_connector_id_connectors")
        ),
        sa.ForeignKeyConstraint(
            ["repository_id"],
            ["repositories.id"],
            name=op.f("fk_documents_repository_id_repositories"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_documents")),
    )
    op.create_index(op.f("ix_documents_content_hash"), "documents", ["content_hash"], unique=False)
    op.create_index(op.f("ix_documents_source"), "documents", ["source"], unique=False)
    op.create_index(op.f("ix_documents_title"), "documents", ["title"], unique=False)
    op.create_table(
        "operational_experiences",
        sa.Column("problem", sa.String(length=500), nullable=False),
        sa.Column(
            "symptoms",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("root_cause", sa.Text(), nullable=True),
        sa.Column("resolution", sa.Text(), nullable=True),
        sa.Column("lessons_learned", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column(
            "source",
            sa.Enum(
                "user_teaching",
                "document_extraction",
                "incident_report",
                name="experiencesource",
                native_enum=False,
                length=30,
            ),
            nullable=False,
        ),
        sa.Column("author", sa.String(length=200), nullable=True),
        sa.Column(
            "related_technologies",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("incident_id", GUID(length=36), nullable=True),
        sa.Column("id", GUID(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["incident_id"],
            ["incidents.id"],
            name=op.f("fk_operational_experiences_incident_id_incidents"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_operational_experiences")),
    )
    op.create_index(
        op.f("ix_operational_experiences_problem"),
        "operational_experiences",
        ["problem"],
        unique=False,
    )
    op.create_index(
        op.f("ix_operational_experiences_source"),
        "operational_experiences",
        ["source"],
        unique=False,
    )
    op.create_table(
        "services",
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("environment", sa.String(length=50), nullable=True),
        sa.Column("namespace", sa.String(length=200), nullable=True),
        sa.Column("runtime", sa.String(length=100), nullable=True),
        sa.Column("sla", sa.String(length=100), nullable=True),
        sa.Column(
            "technology_stack",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("owner_team_id", GUID(length=36), nullable=True),
        sa.Column("repository_id", GUID(length=36), nullable=True),
        sa.Column("id", GUID(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["owner_team_id"], ["teams.id"], name=op.f("fk_services_owner_team_id_teams")
        ),
        sa.ForeignKeyConstraint(
            ["repository_id"],
            ["repositories.id"],
            name=op.f("fk_services_repository_id_repositories"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_services")),
    )
    op.create_index(op.f("ix_services_name"), "services", ["name"], unique=True)
    op.create_table(
        "service_dependencies",
        sa.Column("service_id", GUID(length=36), nullable=False),
        sa.Column("depends_on_id", GUID(length=36), nullable=False),
        sa.ForeignKeyConstraint(
            ["depends_on_id"],
            ["services.id"],
            name=op.f("fk_service_dependencies_depends_on_id_services"),
        ),
        sa.ForeignKeyConstraint(
            ["service_id"],
            ["services.id"],
            name=op.f("fk_service_dependencies_service_id_services"),
        ),
        sa.PrimaryKeyConstraint(
            "service_id", "depends_on_id", name=op.f("pk_service_dependencies")
        ),
    )


def downgrade() -> None:
    """Revert the migration."""
    op.drop_table("service_dependencies")
    op.drop_index(op.f("ix_services_name"), table_name="services")
    op.drop_table("services")
    op.drop_index(op.f("ix_operational_experiences_source"), table_name="operational_experiences")
    op.drop_index(op.f("ix_operational_experiences_problem"), table_name="operational_experiences")
    op.drop_table("operational_experiences")
    op.drop_index(op.f("ix_documents_title"), table_name="documents")
    op.drop_index(op.f("ix_documents_source"), table_name="documents")
    op.drop_index(op.f("ix_documents_content_hash"), table_name="documents")
    op.drop_table("documents")
    op.drop_index(op.f("ix_repositories_name"), table_name="repositories")
    op.drop_table("repositories")
    op.drop_index(op.f("ix_ingestion_jobs_status"), table_name="ingestion_jobs")
    op.drop_table("ingestion_jobs")
    op.drop_index(op.f("ix_incidents_title"), table_name="incidents")
    op.drop_index(op.f("ix_incidents_status"), table_name="incidents")
    op.drop_index(op.f("ix_incidents_severity"), table_name="incidents")
    op.drop_index(op.f("ix_incidents_external_id"), table_name="incidents")
    op.drop_table("incidents")
    op.drop_index(op.f("ix_teams_name"), table_name="teams")
    op.drop_table("teams")
    op.drop_index(op.f("ix_connectors_type"), table_name="connectors")
    op.drop_index(op.f("ix_connectors_name"), table_name="connectors")
    op.drop_table("connectors")
