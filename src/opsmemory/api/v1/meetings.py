"""Meeting endpoints: invite bots, inspect processing state, delete, transcript."""

import uuid

from fastapi import APIRouter, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import select

from opsmemory.api.dependencies import CurrentUserDep, MeetingServiceDep, SessionDep
from opsmemory.api.schemas.meetings import MeetingCreate, MeetingDetailOut, MeetingOut
from opsmemory.core.errors import NotFoundError
from opsmemory.db.models import Meeting, MeetingSummary, MeetingTranscript

router = APIRouter(prefix="/meetings", tags=["meetings"])


@router.post("", response_model=MeetingOut, status_code=status.HTTP_201_CREATED)
async def create_meeting(
    payload: MeetingCreate, service: MeetingServiceDep, user: CurrentUserDep
) -> Meeting:
    """Invite a Recall bot into a meeting.

    With ``incident_id`` the meeting enriches that incident; without one, a
    new incident is auto-created after the transcript is processed.
    """
    return await service.create(
        payload.meeting_url,
        title=payload.title,
        provider=payload.provider,
        organizer=payload.organizer,
        incident_id=payload.incident_id,
    )


@router.get("", response_model=list[MeetingOut])
async def list_meetings(session: SessionDep, user: CurrentUserDep) -> list[Meeting]:
    """List meetings, newest first."""
    return list(
        (await session.execute(select(Meeting).order_by(Meeting.created_at.desc()).limit(100)))
        .scalars()
        .all()
    )


@router.get("/{meeting_id}", response_model=MeetingDetailOut)
async def get_meeting(
    meeting_id: uuid.UUID, service: MeetingServiceDep, session: SessionDep, user: CurrentUserDep
) -> MeetingDetailOut:
    """Return a meeting with transcript/summary/sync status and its summary."""
    meeting = await service.get(meeting_id)
    detail = MeetingDetailOut.model_validate(meeting)
    summary = (
        await session.execute(select(MeetingSummary).where(MeetingSummary.meeting_id == meeting_id))
    ).scalar_one_or_none()
    if summary is not None:
        detail.summary = summary.summary
        detail.structured = summary.structured_json
    return detail


@router.get("/{meeting_id}/transcript", response_class=PlainTextResponse)
async def download_transcript(
    meeting_id: uuid.UUID, session: SessionDep, user: CurrentUserDep
) -> str:
    """Download the raw meeting transcript (traceability, stored in PostgreSQL)."""
    transcript = (
        await session.execute(
            select(MeetingTranscript).where(MeetingTranscript.meeting_id == meeting_id)
        )
    ).scalar_one_or_none()
    if transcript is None:
        raise NotFoundError("Transcript not available", code="TRANSCRIPT_NOT_FOUND")
    return transcript.transcript


@router.delete("/{meeting_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_meeting(
    meeting_id: uuid.UUID, service: MeetingServiceDep, user: CurrentUserDep
) -> None:
    """Intelligently delete a meeting and regenerate its incident's documentation."""
    await service.delete(meeting_id)
