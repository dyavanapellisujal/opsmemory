"""Shared enumerations used across the domain model, storage, and API layers.

String-valued enums are used everywhere so values serialize identically in
the database, API responses, and CLI output.
"""

from enum import StrEnum


class ConnectorType(StrEnum):
    """Kind of external knowledge source a connector integrates with."""

    LOCAL_FILES = "local_files"
    GITHUB = "github"
    HTTP_DOCS = "http_docs"


class ConnectorStatus(StrEnum):
    """Operational status of a configured connector."""

    ACTIVE = "active"
    DISABLED = "disabled"
    ERROR = "error"


class DocumentSource(StrEnum):
    """Origin system of an ingested document."""

    LOCAL_FILES = "local_files"
    GITHUB = "github"
    HTTP_DOCS = "http_docs"
    USER = "user"


class IncidentSeverity(StrEnum):
    """Severity classification for incidents (SEV1 is most critical)."""

    SEV1 = "sev1"
    SEV2 = "sev2"
    SEV3 = "sev3"
    SEV4 = "sev4"


class IncidentStatus(StrEnum):
    """Lifecycle status of an incident."""

    OPEN = "open"
    MITIGATED = "mitigated"
    RESOLVED = "resolved"


class ExperienceSource(StrEnum):
    """How an operational experience entered the platform."""

    USER_TEACHING = "user_teaching"
    DOCUMENT_EXTRACTION = "document_extraction"
    INCIDENT_REPORT = "incident_report"
    MEETING = "meeting"


class MeetingProvider(StrEnum):
    """Video conferencing platform a meeting bot joins."""

    GOOGLE_MEET = "google_meet"
    ZOOM = "zoom"
    MICROSOFT_TEAMS = "microsoft_teams"
    UNKNOWN = "unknown"


class MeetingStatus(StrEnum):
    """Lifecycle of a recorded meeting."""

    SCHEDULED = "scheduled"
    RECORDING = "recording"
    COMPLETED = "completed"
    PROCESSED = "processed"
    FAILED = "failed"


class MemoryKind(StrEnum):
    """Category of a stored semantic memory."""

    CHUNK = "chunk"
    EXPERIENCE = "experience"
    SUMMARY = "summary"


class JobStatus(StrEnum):
    """Lifecycle status of a long-running background job."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
