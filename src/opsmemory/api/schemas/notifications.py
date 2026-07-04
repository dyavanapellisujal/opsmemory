"""Notification schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel


class NotificationOut(BaseModel):
    """A user-facing lifecycle notification."""

    id: uuid.UUID
    kind: str
    title: str
    body: str | None
    incident_id: uuid.UUID | None
    read: bool
    created_at: datetime

    model_config = {"from_attributes": True}
