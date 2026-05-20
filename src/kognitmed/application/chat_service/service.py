"""Chat application service — orchestrates memory + prompt + LLM."""

from __future__ import annotations

from uuid import UUID

import structlog

from kognitmed.application.chat_service.schemas import ChatRequest, ChatResponse
from kognitmed.config import Settings
from kognitmed.domain.prompts.medical_prompts import MEDICAL_SYSTEM_PROMPT
from kognitmed.infrastructure.llm_providers.base_provider import AbstractLLMProvider
from kognitmed.infrastructure.memory.in_memory_store import InMemoryConversationStore

log = structlog.get_logger(__name__)


class ChatService:
    """
    Orchestrates a medical AI conversation.

    Flow:
        1. Load conversation history from memory
        2. Build system prompt
        3. Send full context to LLM provider
        4. Persist assistant response to memory
        5. Return structured response
    """

    def __init__(
        self,
        llm_provider: AbstractLLMProvider,
        memory_store: InMemoryConversationStore,
        settings: Settings,
    ) -> None:
        self._llm = llm_provider
        self._memory = memory_store
        self._settings = settings

    async def chat(self, request: ChatRequest) -> ChatResponse:
        """Process a user message and return the agent's response."""
        conversation_id = request.conversation_id

        # 1. Persist the user message
        await self._memory.add_message(
            conversation_id=conversation_id,
            role="user",
            content=request.message,
        )

        # 2. Build full message context: system prompt + history
        system_prompt = MEDICAL_SYSTEM_PROMPT.render(context="general medical assistance")
        history = await self._memory.get_history(conversation_id)

        messages: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt},
            *history,
        ]

        log.info(
            "chat_request",
            conversation_id=str(conversation_id),
            message_count=len(messages),
            provider=self._llm.provider_name,
            # NOTE: message content is NOT logged to avoid PII exposure
        )

        # 3. Call LLM provider
        assistant_reply = await self._llm.complete(messages)

        # 4. Persist assistant response
        await self._memory.add_message(
            conversation_id=conversation_id,
            role="assistant",
            content=assistant_reply,
        )

        log.info("chat_response", conversation_id=str(conversation_id))

        return ChatResponse(
            conversation_id=conversation_id,
            response=assistant_reply,
            provider=self._llm.provider_name,
        )

    async def get_history(self, conversation_id: UUID) -> list[dict[str, str]]:
        """Return the conversation history (without system prompt)."""
        return await self._memory.get_history(conversation_id)
