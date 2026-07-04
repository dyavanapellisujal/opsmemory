"""Recall.ai client and webhook verification for the Meeting Connector.

The Meeting Connector is push-based: instead of the pull-style
``discover()`` lifecycle of file/HTTP connectors, Recall.ai delivers a
``bot.done`` webhook when a meeting ends. Everything downstream reuses the
same platform pipeline (teaching, memory engine, graph) — see ADR-0007.
"""

import base64
import hashlib
import hmac
from typing import Any
from urllib.parse import urlparse

import httpx

from opsmemory.core.errors import ConnectorError
from opsmemory.domain.enums import MeetingProvider


class RecallClient:
    """Thin async client for the Recall.ai REST API."""

    def __init__(self, api_key: str, region: str, bot_name: str, timeout: float = 30.0) -> None:
        if not api_key:
            raise ConnectorError(
                "Recall.ai is not configured — set OPSMEMORY_RECALL_API_KEY",
                code="RECALL_NOT_CONFIGURED",
            )
        self._base_url = f"https://{region}.recall.ai/api/v1"
        self._headers = {"Authorization": f"Token {api_key}"}
        self._bot_name = bot_name
        self._timeout = timeout

    async def create_bot(self, meeting_url: str) -> dict[str, Any]:
        """Create a meeting bot that joins and transcribes the meeting.

        Uses the meeting-captions transcript provider so no extra
        transcription vendor is required.
        """
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._base_url}/bot/",
                headers=self._headers,
                json={
                    "meeting_url": meeting_url,
                    "bot_name": self._bot_name,
                    "recording_config": {"transcript": {"provider": {"meeting_captions": {}}}},
                },
            )
        if response.status_code not in (200, 201):
            raise ConnectorError(
                f"Recall bot creation failed: HTTP {response.status_code}",
                details={"body": response.text[:500]},
            )
        payload: dict[str, Any] = response.json()
        return payload

    async def get_bot(self, bot_id: str) -> dict[str, Any]:
        """Retrieve a bot, including recordings and media shortcuts."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(f"{self._base_url}/bot/{bot_id}/", headers=self._headers)
        if response.status_code != 200:
            raise ConnectorError(
                f"Recall bot retrieval failed: HTTP {response.status_code}",
                details={"body": response.text[:500]},
            )
        payload: dict[str, Any] = response.json()
        return payload

    async def download_json(self, url: str) -> Any:
        """Download a Recall-provided JSON artifact (e.g. a transcript)."""
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            response = await client.get(url)
        if response.status_code != 200:
            raise ConnectorError(
                f"Recall artifact download failed: HTTP {response.status_code}",
                details={"url": url},
            )
        return response.json()


def transcript_download_url(bot: dict[str, Any]) -> str | None:
    """Extract the transcript download URL from a bot payload."""
    for recording in bot.get("recordings") or []:
        shortcut = (recording.get("media_shortcuts") or {}).get("transcript") or {}
        url = (shortcut.get("data") or {}).get("download_url")
        if url:
            return str(url)
    return None


def recording_download_url(bot: dict[str, Any]) -> str | None:
    """Extract the mixed video/audio recording URL from a bot payload."""
    for recording in bot.get("recordings") or []:
        shortcuts = recording.get("media_shortcuts") or {}
        for key in ("video_mixed", "audio_mixed"):
            url = ((shortcuts.get(key) or {}).get("data") or {}).get("download_url")
            if url:
                return str(url)
    return None


def render_transcript(raw: Any) -> str:
    """Render Recall's transcript JSON into speaker-attributed plain text.

    Input shape: a list of segments, each with a ``participant`` and a list
    of ``words``. Consecutive segments from the same speaker are merged.
    """
    if not isinstance(raw, list):
        return ""
    lines: list[str] = []
    last_speaker: str | None = None
    for segment in raw:
        if not isinstance(segment, dict):
            continue
        participant = segment.get("participant") or {}
        speaker = str(participant.get("name") or "Unknown speaker")
        words = segment.get("words") or []
        text = " ".join(str(w.get("text", "")) for w in words if isinstance(w, dict)).strip()
        if not text:
            continue
        if speaker == last_speaker and lines:
            lines[-1] = f"{lines[-1]} {text}"
        else:
            lines.append(f"{speaker}: {text}")
            last_speaker = speaker
    return "\n".join(lines)


def transcript_participants(raw: Any) -> list[str]:
    """Extract the distinct participant names from Recall's transcript JSON."""
    if not isinstance(raw, list):
        return []
    seen: list[str] = []
    for segment in raw:
        if not isinstance(segment, dict):
            continue
        name = ((segment.get("participant") or {}).get("name") or "").strip()
        if name and name not in seen:
            seen.append(name)
    return seen


def infer_provider(meeting_url: str) -> MeetingProvider:
    """Infer the conferencing platform from the meeting URL."""
    host = urlparse(meeting_url).netloc.lower()
    if "meet.google" in host:
        return MeetingProvider.GOOGLE_MEET
    if "zoom." in host or host.endswith("zoom.us"):
        return MeetingProvider.ZOOM
    if "teams.microsoft" in host or "teams.live" in host:
        return MeetingProvider.MICROSOFT_TEAMS
    return MeetingProvider.UNKNOWN


def verify_svix_signature(secret: str, headers: dict[str, str], body: bytes) -> bool:
    """Verify a Svix webhook signature (Recall delivers webhooks via Svix).

    The signed content is ``{svix-id}.{svix-timestamp}.{body}``, HMAC-SHA256
    with the base64-decoded portion of the ``whsec_`` secret; the signature
    header may contain multiple space-separated ``v1,<base64>`` entries.
    """
    svix_id = headers.get("svix-id", "")
    svix_timestamp = headers.get("svix-timestamp", "")
    svix_signature = headers.get("svix-signature", "")
    if not (svix_id and svix_timestamp and svix_signature):
        return False
    key = base64.b64decode(secret.removeprefix("whsec_"))
    signed = f"{svix_id}.{svix_timestamp}.".encode() + body
    expected = base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode()
    return any(
        hmac.compare_digest(expected, candidate.partition(",")[2])
        for candidate in svix_signature.split(" ")
        if candidate.startswith("v1,")
    )
