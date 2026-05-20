"""Chat message and conversation domain models."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    """A single message in a conversation."""

    id: UUID = Field(default_factory=uuid4)
    role: Literal["user", "assistant", "system"]
    content: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Conversation(BaseModel):
    """A conversation session between the user and the AI agent."""

    id: UUID = Field(default_factory=uuid4)
    messages: list[ChatMessage] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def add_message(self, role: Literal["user", "assistant", "system"], content: str) -> ChatMessage:
        msg = ChatMessage(role=role, content=content)
        self.messages.append(msg)
        return msg

    def get_history(self) -> list[dict[str, str]]:
        """Return messages formatted for LLM providers."""
        return [{"role": m.role, "content": m.content} for m in self.messages]
