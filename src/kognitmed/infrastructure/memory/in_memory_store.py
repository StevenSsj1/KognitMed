"""In-memory conversation store — implements AbstractMemory."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from kognitmed.domain.memory.base_memory import AbstractMemory
from kognitmed.domain.models.message import ChatMessage, Conversation


class InMemoryConversationStore(AbstractMemory):
    """
    Stores conversations in process memory.

    NOTE: Data is lost on restart. Swap this for a persistent backend
    (Redis, PostgreSQL) when moving to production.
    """

    def __init__(self) -> None:
        self._store: dict[UUID, Conversation] = {}

    async def get_or_create_conversation(self, conversation_id: UUID) -> Conversation:
        if conversation_id not in self._store:
            self._store[conversation_id] = Conversation(id=conversation_id)
        return self._store[conversation_id]

    async def add_message(
        self,
        conversation_id: UUID,
        role: Literal["user", "assistant", "system"],
        content: str,
    ) -> ChatMessage:
        conv = await self.get_or_create_conversation(conversation_id)
        return conv.add_message(role=role, content=content)

    async def get_history(self, conversation_id: UUID) -> list[dict[str, str]]:
        if conversation_id not in self._store:
            return []
        return self._store[conversation_id].get_history()

    async def clear(self, conversation_id: UUID) -> None:
        if conversation_id in self._store:
            self._store[conversation_id].messages.clear()

    async def get_conversation(self, conversation_id: UUID) -> Conversation | None:
        return self._store.get(conversation_id)

    async def list_conversations(self) -> list[Conversation]:
        return list(self._store.values())
