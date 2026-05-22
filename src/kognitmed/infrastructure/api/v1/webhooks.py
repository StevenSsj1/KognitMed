"""Evolution API webhook endpoint.

Receives events from Evolution API, validates the request, and delegates
processing to the application service. Responds 200 immediately; heavy
processing happens in a background task.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request

import structlog

from kognitmed.application.evolution_service.service import EvolutionWebhookService
from kognitmed.config import Settings, get_settings
from kognitmed.dependencies import get_evolution_webhook_service
from kognitmed.domain.models.evolution import EvolutionMessageData

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

_SUPPORTED_EVENTS = {"messages.upsert"}


async def _handle_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    service: EvolutionWebhookService,
    settings: Settings,
) -> dict[str, str]:
    """Shared logic for both webhook routes."""
    body: dict[str, Any] = await request.json()

    # Verify API key from body (Evolution sends it in the payload, not headers)
    expected = settings.evolution_webhook_secret or settings.evolution_api_key
    if expected:
        apikey = body.get("apikey", "")
        if apikey != expected:
            log.warning("webhook_auth_failed")
            raise HTTPException(status_code=401, detail="Invalid API key")

    event = body.get("event", "")
    instance = body.get("instance", "")

    log.info("webhook_received", webhook_event=event, instance=instance)

    if event not in _SUPPORTED_EVENTS:
        return {"status": "ignored", "event": event}

    raw_data = body.get("data", {})
    try:
        message_data = EvolutionMessageData.model_validate(raw_data)
        message_data.instance_id = instance
        message_data.reply_jid = body.get("sender", "")
    except Exception:
        log.exception("webhook_parse_error", webhook_event=event)
        return {"status": "parse_error"}

    background_tasks.add_task(_safe_process, service, message_data)
    return {"status": "accepted"}


@router.post(
    "/evolution",
    status_code=200,
    summary="Receive Evolution API webhook events",
)
async def evolution_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    service: Annotated[EvolutionWebhookService, Depends(get_evolution_webhook_service)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, str]:
    return await _handle_webhook(request, background_tasks, service, settings)


@router.post(
    "/evolution/{event_type:path}",
    status_code=200,
    summary="Receive Evolution API webhook events (by event)",
    include_in_schema=False,
)
async def evolution_webhook_by_event(
    request: Request,
    background_tasks: BackgroundTasks,
    event_type: str,
    service: Annotated[EvolutionWebhookService, Depends(get_evolution_webhook_service)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, str]:
    return await _handle_webhook(request, background_tasks, service, settings)


async def _safe_process(
    service: EvolutionWebhookService,
    data: EvolutionMessageData,
) -> None:
    """Wrapper that catches exceptions to avoid crashing background tasks."""
    try:
        await service.handle_messages_upsert(data)
    except Exception:
        log.exception(
            "webhook_process_error",
            message_id=data.key.id,
            sender=data.sender_phone,
        )
