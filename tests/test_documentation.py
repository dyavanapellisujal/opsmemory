"""Tests for the living-documentation generator (pure assembly + citations)."""

import uuid
from types import SimpleNamespace

from opsmemory.domain.enums import IncidentSeverity, IncidentStatus
from opsmemory.incidents.documentation import EvidenceBundle, generate_documentation


def _incident(**over: object) -> SimpleNamespace:
    base = {
        "id": uuid.uuid4(),
        "number": 1042,
        "reference": "INC-1042",
        "title": "Redis outage",
        "description": "payments-api down",
        "severity": IncidentSeverity.SEV2,
        "status": IncidentStatus.RESOLVED,
        "root_cause": "Expired credentials",
        "resolution": "Rotated the secret",
        "lessons_learned": "Rotate before expiry",
    }
    base.update(over)
    return SimpleNamespace(**base)


def test_sections_cite_incident_fields() -> None:
    doc = generate_documentation(EvidenceBundle(incident=_incident()))
    keys = {s.key: s for s in doc.sections}
    assert "Expired credentials" in keys["root_cause"].items[0]
    assert keys["root_cause"].sources[0].type == "manual"
    assert "resolution" in keys and "lessons_learned" in keys


def test_meeting_summary_enriches_with_citations() -> None:
    meeting = SimpleNamespace(
        id=uuid.uuid4(),
        title="Incident call #3",
        status=SimpleNamespace(value="completed"),
        recording_url="https://recall/rec",
    )
    summary = SimpleNamespace(
        structured_json={
            "meeting_summary": "Redis auth failed; rotated secret.",
            "root_cause": "Secret expired 90 days after creation",
            "incident": {"timeline": ["14:02 alerts fired", "14:41 rotated"]},
            "resolution": ["Rotate secret", "Restart deployment"],
            "lessons_learned": ["Alert on secret age"],
            "architecture_decisions": ["Adopt short-lived credentials"],
            "action_items": [{"owner": "alice", "task": "Add expiry alert"}],
            "services": ["payments-api", "redis"],
            "technologies": ["kubernetes"],
        }
    )
    bundle = EvidenceBundle(
        incident=_incident(root_cause=None, resolution=None, lessons_learned=None),
        meetings=[meeting],
        summaries={str(meeting.id): summary},
    )
    doc = generate_documentation(bundle)
    keys = {s.key: s for s in doc.sections}
    assert any("14:02" in item for item in keys["timeline"].items)
    assert "payments-api" in keys["services"].items
    assert any("alice" in item for item in keys["action_items"].items)
    # Every enriched section cites the meeting.
    assert any(src.type == "meeting" for src in keys["root_cause"].sources)
    assert keys["architecture_decisions"].sources[0].ref_id == str(meeting.id)


def test_documents_appear_as_references_and_evidence() -> None:
    document = SimpleNamespace(
        id=uuid.uuid4(),
        title="Redis Runbook",
        url="file:///runbook.md",
        source=SimpleNamespace(value="user"),
        content="# Redis Runbook\n\nRun `SELECT pg_terminate_backend(pid);` to clear locks.",
    )
    doc = generate_documentation(EvidenceBundle(incident=_incident(), documents=[document]))
    keys = {s.key: s for s in doc.sections}
    assert "Redis Runbook" in keys["references"].items
    assert any(s.ref_id == str(document.id) for s in keys["evidence"].sources)
    # The Detailed Summary carries the full document content verbatim (incl. commands).
    detailed = keys["detailed_summary"]
    assert any("pg_terminate_backend" in item for item in detailed.items)
    assert any(s.ref_id == str(document.id) for s in detailed.sources)
