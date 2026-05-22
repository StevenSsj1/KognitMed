"""HTTP client for Evolution API — sends messages back to WhatsApp."""

from __future__ import annotations

import httpx
import structlog

from kognitmed.config import Settings

log = structlog.get_logger(__name__)


class EvolutionAPIClient:
    """Async client to interact with Evolution API REST endpoints."""

    def __init__(self, settings: Settings) -> None:
        self._base_url = settings.evolution_api_url.rstrip("/")
        self._instance = settings.evolution_instance_name
        self._headers = {
            "apikey": settings.evolution_api_key,
            "Content-Type": "application/json",
        }

    async def send_text(self, remote_jid: str, text: str) -> dict:
        """Send a text message to a WhatsApp contact/group.

        Args:
            remote_jid: Destination in format ``<phone>@s.whatsapp.net`` or group JID.
            text: Message body.
        """
        url = f"{self._base_url}/message/sendText/{self._instance}"
        payload = {
            "number": remote_jid,
            "text": text,
        }

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, json=payload, headers=self._headers)

        if response.status_code >= 400:
            log.error(
                "evolution_send_failed",
                status=response.status_code,
                body=response.text[:500],
                remote_jid=remote_jid,
            )
            response.raise_for_status()

        log.info("evolution_message_sent", remote_jid=remote_jid)
        return response.json()
