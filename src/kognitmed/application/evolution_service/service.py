"""Evolution webhook processing service.

Receives normalized webhook events, deduplicates, routes to ChatService,
and sends the AI response back via Evolution API.
"""

from __future__ import annotations

from uuid import UUID, uuid5, NAMESPACE_URL

import structlog

from kognitmed.application.chat_service.schemas import ChatRequest
from kognitmed.application.chat_service.service import ChatService
from kognitmed.application.evolution_service.dedup import MessageDeduplicator
from kognitmed.domain.models.evolution import EvolutionMessageData
from kognitmed.infrastructure.evolution.client import EvolutionAPIClient

log = structlog.get_logger(__name__)


class EvolutionWebhookService:
    """Processes incoming WhatsApp messages from Evolution API webhooks."""

    def __init__(
        self,
        chat_service: ChatService,
        evolution_client: EvolutionAPIClient,
        deduplicator: MessageDeduplicator,
    ) -> None:
        self._chat = chat_service
        self._evo = evolution_client
        self._dedup = deduplicator

    async def handle_messages_upsert(self, data: EvolutionMessageData) -> None:
        """Process an incoming message event.

        Skips: messages from self, duplicates, non-text messages, and group chats.
        """
        # Skip own messages
        if data.key.from_me:
            return

        # Skip group messages (can be enabled later)
        if data.is_group:
            log.debug("evolution_skip_group", remote_jid=data.key.remote_jid)
            return

        # Deduplication by instance + message ID
        dedup_key = f"{data.instance_id}:{data.key.id}"
        if self._dedup.is_duplicate(dedup_key):
            log.debug("evolution_duplicate", message_id=data.key.id)
            return

        # Extract text content
        text = data.text
        if not text:
            log.info(
                "evolution_skip_non_text",
                message_type=data.message_type,
                message_id=data.key.id,
            )
            return

        # Derive a stable conversation ID from the sender's JID
        conversation_id = self._jid_to_conversation_id(data.key.remote_jid)

        log.info(
            "evolution_incoming",
            sender=data.sender_phone,
            push_name=data.push_name,
            conversation_id=str(conversation_id),
        )

        # Route to ChatService
        chat_request = ChatRequest(
            conversation_id=conversation_id,
            message=text[:4096],
        )
        chat_response = await self._chat.chat(chat_request)

        # Send AI response back via WhatsApp
        await self._evo.send_text(
            remote_jid=data.key.remote_jid,
            text=chat_response.response,
        )

        log.info(
            "evolution_reply_sent",
            conversation_id=str(conversation_id),
            sender=data.sender_phone,
        )

    @staticmethod
    def _jid_to_conversation_id(remote_jid: str) -> UUID:
        """Derive a deterministic UUID from a WhatsApp JID.

        This ensures the same contact always maps to the same conversation.
        """
        return uuid5(NAMESPACE_URL, f"whatsapp:{remote_jid}")
