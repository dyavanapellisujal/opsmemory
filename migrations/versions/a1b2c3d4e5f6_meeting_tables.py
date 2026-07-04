"""meeting tables.

Revision ID: a1b2c3d4e5f6
Revises: 77758038bee6
Create Date: 2026-07-03 19:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from opsmemory.db.types import GUID

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "77758038bee6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply the migration."""
    op.create_table(
        "meetings",
        sa.Column("recall_bot_id", sa.String(length=100), nullable=False),
        sa.Column("meeting_url", sa.String(length=2000), nullable=False),
        sa.Column(
            "provider",
            sa.Enum(
                "google_meet",
                "zoom",
                "microsoft_teams",
                "unknown",
                name="meetingprovider",
                native_enum=False,
                length=30,
            ),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("organizer", sa.String(length=200), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "scheduled",
                "recording",
                "completed",
                "processed",
                "failed",
                name="meetingstatus",
                native_enum=False,
                length=30,
            ),
            nullable=False,
        ),
        sa.Column("recording_url", sa.String(length=2000), nullable=True),
        sa.Column("transcript_url", sa.String(length=2000), nullable=True),
        sa.Column("transcript_downloaded", sa.Boolean(), nullable=False),
        sa.Column("summary_generated", sa.Boolean(), nullable=False),
        sa.Column("cognee_synced", sa.Boolean(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.Column("id", GUID(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_meetings")),
        sa.UniqueConstraint("recall_bot_id", name=op.f("uq_meetings_recall_bot_id")),
    )
    op.create_index(
        op.f("ix_meetings_recall_bot_id"), "meetings", ["recall_bot_id"], unique=True
    )
    op.create_index(op.f("ix_meetings_status"), "meetings", ["status"], unique=False)

    op.create_table(
        "meeting_transcripts",
        sa.Column("meeting_id", GUID(length=36), nullable=False),
        sa.Column("transcript", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("id", GUID(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["meeting_id"],
            ["meetings.id"],
            name=op.f("fk_meeting_transcripts_meeting_id_meetings"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_meeting_transcripts")),
        sa.UniqueConstraint("meeting_id", name=op.f("uq_meeting_transcripts_meeting_id")),
    )
    op.create_index(
        op.f("ix_meeting_transcripts_meeting_id"),
        "meeting_transcripts",
        ["meeting_id"],
        unique=True,
    )

    op.create_table(
        "meeting_summaries",
        sa.Column("meeting_id", GUID(length=36), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column(
            "structured_json",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("id", GUID(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["meeting_id"],
            ["meetings.id"],
            name=op.f("fk_meeting_summaries_meeting_id_meetings"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_meeting_summaries")),
        sa.UniqueConstraint("meeting_id", name=op.f("uq_meeting_summaries_meeting_id")),
    )
    op.create_index(
        op.f("ix_meeting_summaries_meeting_id"),
        "meeting_summaries",
        ["meeting_id"],
        unique=True,
    )


def downgrade() -> None:
    """Revert the migration."""
    op.drop_index(op.f("ix_meeting_summaries_meeting_id"), table_name="meeting_summaries")
    op.drop_table("meeting_summaries")
    op.drop_index(op.f("ix_meeting_transcripts_meeting_id"), table_name="meeting_transcripts")
    op.drop_table("meeting_transcripts")
    op.drop_index(op.f("ix_meetings_status"), table_name="meetings")
    op.drop_index(op.f("ix_meetings_recall_bot_id"), table_name="meetings")
    op.drop_table("meetings")
