"""Chat API endpoints — the primary interface to the medical AI agent."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from kognitmed.application.chat_service.schemas import ChatRequest, ChatResponse
from kognitmed.application.chat_service.service import ChatService
from kognitmed.dependencies import get_chat_service

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse, summary="Send a message to the medical AI agent")
async def chat(
    request: ChatRequest,
    service: Annotated[ChatService, Depends(get_chat_service)],
) -> ChatResponse:
    """
    Send a message to KognitMed and receive an AI-generated medical response.

    - Send the same `conversation_id` to continue an existing conversation.
    - Omit `conversation_id` to start a new conversation (one is auto-generated).
    """
    return await service.chat(request)


@router.get(
    "/{conversation_id}/history",
    summary="Get conversation history",
)
async def get_history(
    conversation_id: UUID,
    service: Annotated[ChatService, Depends(get_chat_service)],
) -> list[dict[str, str]]:
    """Retrieve the full message history for a conversation."""
    return await service.get_history(conversation_id)
