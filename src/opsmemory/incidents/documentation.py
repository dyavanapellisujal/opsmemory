"""Living documentation: assemble cited incident docs from all evidence.

Documentation is never hand-edited — it is regenerated from the incident's
documents, meeting summaries, operational experiences, and manual entries.
Every section carries the sources it was derived from so the UI can link
back to the original evidence.
"""

import uuid
from typing import Any

from pydantic import BaseModel, Field

from opsmemory.db.models import Document, Incident, Meeting, MeetingSummary, OperationalExperience


class Source(BaseModel):
    """A citation pointing at the evidence a statement came from."""

    type: str = Field(description="meeting|document|experience|manual")
    label: str
    ref_id: str | None = None
    url: str | None = None


class DocSection(BaseModel):
    """One section of the living documentation with its citations."""

    key: str
    title: str
    items: list[str] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        """True when the section has no content."""
        return not self.items


class LivingDocumentation(BaseModel):
    """The full regenerated documentation for an incident."""

    sections: list[DocSection]

    def model_dump_doc(self) -> dict[str, Any]:
        """Serialize for storage on ``Incident.documentation``."""
        return self.model_dump(mode="json")


class EvidenceBundle(BaseModel):
    """Everything linked to an incident, used to (re)generate documentation."""

    incident: Any
    documents: list[Any] = Field(default_factory=list)
    meetings: list[Any] = Field(default_factory=list)
    summaries: dict[str, Any] = Field(default_factory=dict)  # meeting_id -> MeetingSummary
    experiences: list[Any] = Field(default_factory=list)

    model_config = {"arbitrary_types_allowed": True}


def _doc_source(document: Document) -> Source:
    """Citation for an uploaded document."""
    kind = "manual" if document.source.value == "user" else "document"
    return Source(type=kind, label=document.title, ref_id=str(document.id), url=document.url)


def _meeting_source(meeting: Meeting) -> Source:
    """Citation for a meeting."""
    return Source(
        type="meeting",
        label=meeting.title or f"Meeting {str(meeting.id)[:8]}",
        ref_id=str(meeting.id),
        url=meeting.recording_url,
    )


def _experience_source(experience: OperationalExperience) -> Source:
    """Citation for an operational experience."""
    return Source(
        type="experience",
        label=f"Operational experience: {experience.problem[:60]}",
        ref_id=str(experience.id),
    )


def generate_documentation(bundle: EvidenceBundle) -> LivingDocumentation:
    """Assemble cited documentation from an incident's evidence bundle."""
    incident: Incident = bundle.incident
    sections: dict[str, DocSection] = {
        key: DocSection(key=key, title=title)
        for key, title in (
            ("overview", "Overview"),
            ("timeline", "Timeline"),
            ("summary", "Incident Summary"),
            ("detailed_summary", "Detailed Summary"),
            ("root_cause", "Root Cause"),
            ("resolution", "Resolution"),
            ("lessons_learned", "Lessons Learned"),
            ("architecture_decisions", "Architecture Decisions"),
            ("action_items", "Action Items"),
            ("services", "Services"),
            ("infrastructure", "Infrastructure"),
            ("references", "References"),
            ("evidence", "Evidence"),
        )
    }

    def add(key: str, text: str | None, source: Source | None) -> None:
        text = (text or "").strip()
        if not text:
            return
        section = sections[key]
        if text not in section.items:
            section.items.append(text)
        if source is not None and not any(
            s.ref_id == source.ref_id and s.type == source.type for s in section.sources
        ):
            section.sources.append(source)

    # --- Incident's own fields (manual metadata) ---
    manual = Source(type="manual", label="Incident record")
    add("overview", incident.description, manual)
    add("summary", incident.description, manual)
    add("root_cause", incident.root_cause, manual)
    add("resolution", incident.resolution, manual)
    add("lessons_learned", incident.lessons_learned, manual)

    # --- Meeting summaries (structured incident extraction) ---
    for meeting in bundle.meetings:
        summary: MeetingSummary | None = bundle.summaries.get(str(meeting.id))
        src = _meeting_source(meeting)
        sections["evidence"].sources.append(src)
        sections["evidence"].items.append(
            f"Meeting: {meeting.title or meeting.id} ({meeting.status.value})"
        )
        if summary is None:
            continue
        data = summary.structured_json or {}
        meeting_summary = str(data.get("meeting_summary") or "")
        add("summary", meeting_summary, src)
        # Full meeting narrative preserved verbatim in the detailed block
        # (rendered as markdown by the UI); the citation identifies the source.
        if meeting_summary:
            add("detailed_summary", meeting_summary, src)
        add("root_cause", data.get("root_cause"), src)
        incident_block = data.get("incident") or {}
        for event in incident_block.get("timeline") or []:
            add("timeline", str(event), src)
        for step in data.get("resolution") or []:
            add("resolution", str(step), src)
        for lesson in data.get("lessons_learned") or []:
            add("lessons_learned", str(lesson), src)
        for decision in data.get("architecture_decisions") or []:
            add("architecture_decisions", str(decision), src)
        for item in data.get("action_items") or []:
            owner = item.get("owner") or "unassigned"
            add("action_items", f"{owner}: {item.get('task', '')}", src)
        for service in data.get("services") or []:
            add("services", str(service), src)
        for tech in data.get("technologies") or []:
            add("infrastructure", str(tech), src)

    # --- Operational experiences ---
    for experience in bundle.experiences:
        src = _experience_source(experience)
        add("root_cause", experience.root_cause, src)
        add("resolution", experience.resolution, src)
        add("lessons_learned", experience.lessons_learned, src)
        for tech in experience.related_technologies or []:
            add("infrastructure", str(tech), src)

    # --- Documents: full content in the detailed block + references + evidence ---
    for document in bundle.documents:
        src = _doc_source(document)
        # The complete uploaded content (rendered as markdown by the UI — code
        # blocks, SQL, commands and all), so the page shows the full detail.
        content = (document.content or "").strip()
        if content:
            add("detailed_summary", content, src)
        sections["references"].items.append(document.title)
        sections["references"].sources.append(src)
        sections["evidence"].items.append(f"Document: {document.title}")
        sections["evidence"].sources.append(src)

    # --- Overview fallback ---
    if sections["overview"].is_empty:
        add(
            "overview",
            f"{incident.reference}: {incident.title} "
            f"(severity {incident.severity.value}, status {incident.status.value}).",
            manual,
        )

    return LivingDocumentation(sections=[s for s in sections.values() if not s.is_empty])


def stable_uuid_str(value: uuid.UUID | None) -> str | None:
    """Render a UUID as a string, or None."""
    return str(value) if value is not None else None
