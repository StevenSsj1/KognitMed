"""Abstract memory interface for the AI agent."""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from kognitmed.domain.models.message import ChatMessage, Conversation


class AbstractMemory(ABC):
    """Interface for conversation memory backends."""

    @abstractmethod
    async def get_or_create_conversation(self, conversation_id: UUID) -> Conversation:
        """Retrieve an existing conversation or create a new one."""
        ...

    @abstractmethod
    async def add_message(
        self,
        conversation_id: UUID,
        role: str,
        content: str,
    ) -> ChatMessage:
        """Add a message to the conversation."""
        ...

    @abstractmethod
    async def get_history(self, conversation_id: UUID) -> list[dict[str, str]]:
        """Return the full message history in LLM-ready format."""
        ...

    @abstractmethod
    async def clear(self, conversation_id: UUID) -> None:
        """Clear all messages for a conversation."""
        ...
