"""memories table.

Revision ID: 77758038bee6
Revises: d2081a9dbf78
Create Date: 2026-07-03 11:27:59.837588
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from opsmemory.db.types import GUID, PortableVector

revision: str = "77758038bee6"
down_revision: str | None = "d2081a9dbf78"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply the migration."""
    op.create_table(
        "memories",
        sa.Column(
            "kind",
            sa.Enum(
                "chunk", "experience", "summary", name="memorykind", native_enum=False, length=30
            ),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("section", sa.String(length=500), nullable=True),
        sa.Column("embedding", PortableVector(), nullable=True),
        sa.Column("embedding_model", sa.String(length=100), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "meta",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("document_id", GUID(length=36), nullable=True),
        sa.Column("experience_id", GUID(length=36), nullable=True),
        sa.Column("id", GUID(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_memories_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["experience_id"],
            ["operational_experiences.id"],
            name=op.f("fk_memories_experience_id_operational_experiences"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_memories")),
    )
    op.create_index(op.f("ix_memories_content_hash"), "memories", ["content_hash"], unique=False)
    op.create_index(op.f("ix_memories_document_id"), "memories", ["document_id"], unique=False)
    op.create_index(op.f("ix_memories_experience_id"), "memories", ["experience_id"], unique=False)
    op.create_index(op.f("ix_memories_kind"), "memories", ["kind"], unique=False)
    # ANN index for semantic search; HNSW gives good recall/latency without tuning.
    op.create_index(
        "ix_memories_embedding_hnsw",
        "memories",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def downgrade() -> None:
    """Revert the migration."""
    op.drop_index("ix_memories_embedding_hnsw", table_name="memories")
    op.drop_index(op.f("ix_memories_kind"), table_name="memories")
    op.drop_index(op.f("ix_memories_experience_id"), table_name="memories")
    op.drop_index(op.f("ix_memories_document_id"), table_name="memories")
    op.drop_index(op.f("ix_memories_content_hash"), table_name="memories")
    op.drop_table("memories")
