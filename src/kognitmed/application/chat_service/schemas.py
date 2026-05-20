"""Chat service schemas — request/response contracts."""

from __future__ import annotations

from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Incoming chat request."""

    conversation_id: UUID = Field(
        default_factory=uuid4,
        description="Conversation ID. Send the same ID to continue a conversation.",
    )
    message: str = Field(
        min_length=1,
        max_length=4096,
        description="The user's message to the medical AI agent.",
    )


class ChatResponse(BaseModel):
    """Response from the medical AI agent."""

    conversation_id: UUID
    response: str
    provider: str
