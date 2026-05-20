"""Shared FastAPI dependencies."""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from kognitmed.application.chat_service.service import ChatService
from kognitmed.config import Settings, get_settings
from kognitmed.infrastructure.llm_providers import build_llm_provider
from kognitmed.infrastructure.memory.in_memory_store import InMemoryConversationStore


@lru_cache
def get_conversation_store() -> InMemoryConversationStore:
    return InMemoryConversationStore()


def get_chat_service(
    settings: Annotated[Settings, Depends(get_settings)],
    store: Annotated[InMemoryConversationStore, Depends(get_conversation_store)],
) -> ChatService:
    provider = build_llm_provider(settings)
    return ChatService(llm_provider=provider, memory_store=store, settings=settings)
