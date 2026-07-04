"""Document endpoints."""

import uuid

from fastapi import APIRouter, Query
from sqlalchemy import select

from opsmemory.api.dependencies import SessionDep
from opsmemory.api.schemas.knowledge import DocumentDetailOut, DocumentOut
from opsmemory.core.errors import NotFoundError
from opsmemory.db.models import Document

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("", response_model=list[DocumentOut])
async def list_documents(
    session: SessionDep,
    source: str | None = Query(default=None, description="Filter by source system."),
    tag: str | None = Query(default=None, description="Filter by tag."),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[Document]:
    """List ingested documents with optional filters."""
    stmt = select(Document).order_by(Document.updated_at.desc()).limit(limit).offset(offset)
    if source:
        stmt = stmt.where(Document.source == source)
    rows = list((await session.execute(stmt)).scalars().all())
    if tag:
        rows = [d for d in rows if tag in (d.tags or [])]
    return rows


@router.get("/{document_id}", response_model=DocumentDetailOut)
async def get_document(document_id: uuid.UUID, session: SessionDep) -> Document:
    """Return one document including its full content."""
    document = (
        await session.execute(select(Document).where(Document.id == document_id))
    ).scalar_one_or_none()
    if document is None:
        raise NotFoundError(f"Document {document_id} not found", code="DOCUMENT_NOT_FOUND")
    return document
