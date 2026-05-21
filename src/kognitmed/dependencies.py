"""Shared FastAPI dependencies."""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from kognitmed.application.chat_service.service import ChatService
from kognitmed.application.orientador_service.service import MediOrientadorService
from kognitmed.config import Settings, get_settings
from kognitmed.infrastructure.llm_providers import build_llm_provider, build_llm_provider_for_layer
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


def get_orientador_service(
    settings: Annotated[Settings, Depends(get_settings)],
    store: Annotated[InMemoryConversationStore, Depends(get_conversation_store)],
) -> MediOrientadorService:
    """Dependency for MediOrientadorService.

    Builds two independent LLM providers:
    - extraction_llm: fast/cheap model for structured JSON symptom extraction.
    - synthesis_llm:  capable model for warm conversational response generation.

    Both share the same provider type (openai/gemini) but can use different models
    via ORIENTADOR_EXTRACTION_MODEL and ORIENTADOR_SYNTHESIS_MODEL in .env.
    """
    extraction_llm = build_llm_provider_for_layer(settings, layer="extraction")
    synthesis_llm = build_llm_provider_for_layer(settings, layer="synthesis")
    return MediOrientadorService(
        extraction_llm=extraction_llm,
        synthesis_llm=synthesis_llm,
        memory_store=store,
        settings=settings,
    )
