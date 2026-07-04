"""ORM models for all OpsMemory domain entities.

Importing this package registers every model on the shared declarative
``Base.metadata``, which Alembic uses as the migration target.
"""

from opsmemory.db.models.connector import Connector, IngestionJob
from opsmemory.db.models.document import Document
from opsmemory.db.models.experience import OperationalExperience
from opsmemory.db.models.incident import Incident, IncidentLink
from opsmemory.db.models.meeting import Meeting, MeetingSummary, MeetingTranscript
from opsmemory.db.models.memory import Memory
from opsmemory.db.models.repository import Repository
from opsmemory.db.models.service import Service, service_dependencies
from opsmemory.db.models.team import Team
from opsmemory.db.models.timeline import IncidentEvent, Notification
from opsmemory.db.models.user import Session, User

__all__ = [
    "Connector",
    "Document",
    "Incident",
    "IncidentEvent",
    "IncidentLink",
    "IngestionJob",
    "Meeting",
    "MeetingSummary",
    "MeetingTranscript",
    "Memory",
    "Notification",
    "OperationalExperience",
    "Repository",
    "Service",
    "Session",
    "Team",
    "User",
    "service_dependencies",
]
