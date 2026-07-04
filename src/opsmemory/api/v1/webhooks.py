"""Inbound webhook endpoints (Recall.ai).

The handler verifies the Svix signature (when a secret is configured),
records the event, schedules background processing, and acknowledges
immediately — it never blocks on transcript download or AI work.
"""

import json

from fastapi import APIRouter, Request

from opsmemory.api.dependencies import MeetingServiceDep, SettingsDep
from opsmemory.api.schemas.meetings import WebhookAck
from opsmemory.connectors.recall import verify_svix_signature
from opsmemory.core.errors import ValidationFailedError
from opsmemory.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/recall", response_model=WebhookAck)
async def recall_webhook(
    request: Request, service: MeetingServiceDep, settings: SettingsDep
) -> WebhookAck:
    """Receive Recall.ai bot lifecycle events (Svix-delivered)."""
    body = await request.body()
    if settings.recall_webhook_secret and not verify_svix_signature(
        settings.recall_webhook_secret, dict(request.headers), body
    ):
        raise ValidationFailedError(
            "Invalid webhook signature", code="WEBHOOK_SIGNATURE_INVALID", status_code=401
        )
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ValidationFailedError("Webhook body is not JSON", code="WEBHOOK_INVALID") from exc
    event = str(payload.get("event") or "")
    handled = await service.handle_event(event, payload)
    return WebhookAck(ok=True, handled=handled)
