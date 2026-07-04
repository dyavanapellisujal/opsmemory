"""Tests for the Meeting Connector: Recall client, extraction, webhook, service pipeline."""

import json
import uuid
from typing import Any
from unittest.mock import AsyncMock

from httpx import AsyncClient

from opsmemory.connectors.recall import (
    infer_provider,
    render_transcript,
    verify_svix_signature,
)
from opsmemory.domain.enums import (
    IncidentSeverity,
    IncidentStatus,
    MeetingProvider,
)
from opsmemory.meetings.extraction import (
    IncidentExtraction,
    MeetingExtraction,
    OpExExtraction,
    _fallback_extraction,
    _parse_extraction,
    _strip_fences,
    extract_incident_knowledge,
)

# ---------------------------------------------------------------------------
# render_transcript
# ---------------------------------------------------------------------------


class TestRenderTranscript:
    def test_speaker_attribution(self) -> None:
        raw = [
            {
                "participant": {"name": "Alice"},
                "words": [{"text": "The"}, {"text": "database"}, {"text": "is"}, {"text": "down."}],
            },
            {
                "participant": {"name": "Bob"},
                "words": [{"text": "Checking"}, {"text": "now."}],
            },
        ]
        result = render_transcript(raw)
        assert "Alice: The database is down." in result
        assert "Bob: Checking now." in result

    def test_consecutive_speaker_merging(self) -> None:
        raw = [
            {"participant": {"name": "Alice"}, "words": [{"text": "First."}]},
            {"participant": {"name": "Alice"}, "words": [{"text": "Second."}]},
        ]
        result = render_transcript(raw)
        assert result == "Alice: First. Second."

    def test_empty_input(self) -> None:
        assert render_transcript([]) == ""
        assert render_transcript("not a list") == ""

    def test_missing_participant(self) -> None:
        raw = [{"participant": {}, "words": [{"text": "Hello"}]}]
        result = render_transcript(raw)
        assert "Unknown speaker: Hello" in result

    def test_skips_empty_words(self) -> None:
        raw = [{"participant": {"name": "Alice"}, "words": []}]
        result = render_transcript(raw)
        assert result == ""


# ---------------------------------------------------------------------------
# infer_provider
# ---------------------------------------------------------------------------


class TestInferProvider:
    def test_google_meet(self) -> None:
        assert infer_provider("https://meet.google.com/abc-defg-hij") == MeetingProvider.GOOGLE_MEET

    def test_zoom(self) -> None:
        assert infer_provider("https://us06web.zoom.us/j/123456") == MeetingProvider.ZOOM

    def test_teams(self) -> None:
        url = "https://teams.microsoft.com/l/meetup-join/abc"
        assert infer_provider(url) == MeetingProvider.MICROSOFT_TEAMS

    def test_unknown(self) -> None:
        assert infer_provider("https://example.com/meeting") == MeetingProvider.UNKNOWN


# ---------------------------------------------------------------------------
# verify_svix_signature
# ---------------------------------------------------------------------------


class TestVerifySvixSignature:
    def test_missing_headers_returns_false(self) -> None:
        assert not verify_svix_signature("whsec_abc", {}, b"body")
        assert not verify_svix_signature("whsec_abc", {"svix-id": "id"}, b"body")

    def test_invalid_signature_returns_false(self) -> None:
        headers = {
            "svix-id": "msg_123",
            "svix-timestamp": "1234567890",
            "svix-signature": "v1,invalidbase64sig",
        }
        assert not verify_svix_signature("whsec_dGVzdA==", headers, b'{"event":"test"}')


# ---------------------------------------------------------------------------
# Extraction models
# ---------------------------------------------------------------------------


class TestExtractionModels:
    def test_incident_severity_enum_valid(self) -> None:
        inc = IncidentExtraction(title="test", severity="sev1", status="resolved")
        assert inc.severity_enum() == IncidentSeverity.SEV1
        assert inc.status_enum() == IncidentStatus.RESOLVED

    def test_incident_severity_enum_default(self) -> None:
        inc = IncidentExtraction(title="test", severity="unknown", status="weird")
        assert inc.severity_enum() == IncidentSeverity.SEV3
        assert inc.status_enum() == IncidentStatus.OPEN

    def test_meeting_extraction_defaults(self) -> None:
        ext = MeetingExtraction()
        assert ext.meeting_summary == ""
        assert ext.incident is None
        assert ext.services == []
        assert ext.operational_experience is None

    def test_meeting_extraction_model_dump_roundtrip(self) -> None:
        ext = MeetingExtraction(
            meeting_summary="Redis auth failure",
            incident=IncidentExtraction(title="Redis outage", severity="sev2"),
            services=["auth-service", "redis-cluster"],
            operational_experience=OpExExtraction(
                problem="Redis auth failed",
                resolution="Rotated credentials",
                lesson="Automate credential rotation",
            ),
        )
        dumped = ext.model_dump(mode="json")
        restored = MeetingExtraction.model_validate(dumped)
        assert restored.meeting_summary == ext.meeting_summary
        assert restored.incident is not None
        assert restored.incident.title == "Redis outage"
        assert restored.operational_experience is not None
        assert restored.operational_experience.lesson == "Automate credential rotation"


# ---------------------------------------------------------------------------
# _parse_extraction
# ---------------------------------------------------------------------------


class TestParseExtraction:
    def test_valid_full_json(self) -> None:
        data: dict[str, Any] = {
            "meeting_summary": "Discussed Redis outage",
            "incident": {
                "title": "Redis authentication failure",
                "severity": "sev2",
                "status": "resolved",
                "timeline": ["14:00 - Alert fired", "14:15 - Root cause identified"],
            },
            "services": ["auth-service", "redis-cluster"],
            "technologies": ["redis", "kubernetes"],
            "root_cause": "Expired credentials",
            "contributing_factors": ["No rotation policy"],
            "resolution": ["Rotated credentials", "Restarted pods"],
            "preventative_actions": ["Automate rotation"],
            "lessons_learned": ["Always rotate credentials"],
            "action_items": [
                {"owner": "Alice", "task": "Set up rotation cron"},
                {"owner": None, "task": "Update runbook"},
            ],
            "architecture_decisions": ["Move to IAM-based auth"],
            "operational_experience": {
                "problem": "Redis auth expired",
                "resolution": "Rotated creds",
                "lesson": "Automate rotation",
            },
        }
        result = _parse_extraction(data)
        assert result.meeting_summary == "Discussed Redis outage"
        assert result.incident is not None
        assert result.incident.title == "Redis authentication failure"
        assert len(result.incident.timeline) == 2
        assert result.services == ["auth-service", "redis-cluster"]
        assert result.root_cause == "Expired credentials"
        assert len(result.action_items) == 2
        assert result.action_items[0].owner == "Alice"
        assert result.operational_experience is not None
        assert result.operational_experience.lesson == "Automate rotation"

    def test_minimal_json(self) -> None:
        data: dict[str, Any] = {"meeting_summary": "Quick sync"}
        result = _parse_extraction(data)
        assert result.meeting_summary == "Quick sync"
        assert result.incident is None
        assert result.services == []

    def test_null_incident(self) -> None:
        data: dict[str, Any] = {"meeting_summary": "test", "incident": None}
        result = _parse_extraction(data)
        assert result.incident is None

    def test_empty_incident_title(self) -> None:
        data: dict[str, Any] = {"meeting_summary": "test", "incident": {"title": ""}}
        result = _parse_extraction(data)
        assert result.incident is None


# ---------------------------------------------------------------------------
# _strip_fences
# ---------------------------------------------------------------------------


class TestStripFences:
    def test_no_fences(self) -> None:
        assert _strip_fences('{"key": "value"}') == '{"key": "value"}'

    def test_json_fences(self) -> None:
        raw = '```json\n{"key": "value"}\n```'
        assert _strip_fences(raw) == '{"key": "value"}'

    def test_plain_fences(self) -> None:
        raw = '```\n{"key": "value"}\n```'
        assert _strip_fences(raw) == '{"key": "value"}'


# ---------------------------------------------------------------------------
# _fallback_extraction
# ---------------------------------------------------------------------------


class TestFallbackExtraction:
    def test_truncates_to_500_chars(self) -> None:
        long_text = "word " * 200
        result = _fallback_extraction(long_text)
        assert len(result.meeting_summary) <= 500
        assert result.incident is None

    def test_empty_transcript(self) -> None:
        result = _fallback_extraction("")
        assert result.meeting_summary == "No transcript content available."


# ---------------------------------------------------------------------------
# extract_incident_knowledge (async)
# ---------------------------------------------------------------------------


class TestExtractIncidentKnowledge:
    async def test_no_llm_returns_fallback(self) -> None:
        result = await extract_incident_knowledge(None, "Some transcript text")
        assert result.meeting_summary == "Some transcript text"
        assert result.incident is None

    async def test_llm_returns_valid_json(self) -> None:
        llm_response = json.dumps(
            {
                "meeting_summary": "Redis outage discussed",
                "incident": {
                    "title": "Redis down",
                    "severity": "sev1",
                    "status": "resolved",
                    "timeline": [],
                },
                "services": ["redis"],
                "technologies": ["redis"],
                "root_cause": "OOM killer",
                "contributing_factors": [],
                "resolution": ["Increased memory"],
                "preventative_actions": [],
                "lessons_learned": ["Monitor memory"],
                "action_items": [{"owner": "Bob", "task": "Add alerts"}],
                "architecture_decisions": [],
                "operational_experience": {
                    "problem": "Redis OOM",
                    "resolution": "Increased limits",
                    "lesson": "Set memory limits",
                },
            }
        )
        mock_llm = AsyncMock()
        mock_llm.complete = AsyncMock(return_value=llm_response)
        result = await extract_incident_knowledge(mock_llm, "transcript text")
        assert result.meeting_summary == "Redis outage discussed"
        assert result.incident is not None
        assert result.incident.severity_enum() == IncidentSeverity.SEV1
        assert result.root_cause == "OOM killer"
        assert result.operational_experience is not None

    async def test_llm_invalid_json_falls_back(self) -> None:
        mock_llm = AsyncMock()
        mock_llm.complete = AsyncMock(return_value="This is not JSON at all")
        result = await extract_incident_knowledge(mock_llm, "transcript text")
        # Should fall back gracefully
        assert result.meeting_summary == "transcript text"

    async def test_llm_exception_falls_back(self) -> None:
        mock_llm = AsyncMock()
        mock_llm.complete = AsyncMock(side_effect=RuntimeError("API timeout"))
        result = await extract_incident_knowledge(mock_llm, "transcript text")
        assert result.meeting_summary == "transcript text"


# ---------------------------------------------------------------------------
# Webhook API endpoint
# ---------------------------------------------------------------------------


class TestWebhookEndpoint:
    async def test_webhook_bot_done_acknowledged(self, client: AsyncClient) -> None:
        """Webhook for an unknown bot returns ok=True, handled=False."""
        payload = {"event": "bot.done", "data": {"bot": {"id": "unknown-bot-id"}}}
        response = await client.post(
            "/api/v1/webhooks/recall",
            json=payload,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["ok"] is True
        assert body["handled"] is False  # no matching meeting in DB

    async def test_webhook_invalid_json(self, client: AsyncClient) -> None:
        response = await client.post(
            "/api/v1/webhooks/recall",
            content=b"not json",
            headers={"content-type": "application/json"},
        )
        assert response.status_code == 422

    async def test_webhook_no_bot_id(self, client: AsyncClient) -> None:
        payload = {"event": "bot.done", "data": {}}
        response = await client.post("/api/v1/webhooks/recall", json=payload)
        assert response.status_code == 200
        assert response.json()["handled"] is False


# ---------------------------------------------------------------------------
# Meeting API endpoints
# ---------------------------------------------------------------------------


class TestMeetingEndpoints:
    async def test_list_meetings_empty(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/meetings")
        assert response.status_code == 200
        assert response.json() == []

    async def test_get_meeting_not_found(self, client: AsyncClient) -> None:
        fake_id = str(uuid.uuid4())
        response = await client.get(f"/api/v1/meetings/{fake_id}")
        assert response.status_code == 404

    async def test_create_meeting_no_recall_key(self, client: AsyncClient) -> None:
        """Without RECALL_API_KEY, creating a meeting returns 503."""
        response = await client.post(
            "/api/v1/meetings",
            json={"meeting_url": "https://meet.google.com/abc-defg-hij"},
        )
        assert response.status_code == 503


# ---------------------------------------------------------------------------
# MeetingService pipeline (integration-style with mocks)
# ---------------------------------------------------------------------------


class TestMeetingServicePipeline:
    async def test_handle_event_unknown_bot(self, app: Any) -> None:
        service = app.state.meeting_service
        result = await service.handle_event("bot.done", {"data": {"bot": {"id": "nonexistent"}}})
        assert result is False

    async def test_handle_event_empty_payload(self, app: Any) -> None:
        service = app.state.meeting_service
        result = await service.handle_event("bot.done", {})
        assert result is False
