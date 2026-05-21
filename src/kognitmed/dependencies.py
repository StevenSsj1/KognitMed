"""Shared FastAPI dependencies."""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from kognitmed.application.chat_service.service import ChatService
from kognitmed.application.orientador_service.service import MediOrientadorService
from kognitmed.config import Settings, get_settings
from kognitmed.infrastructure.database.chroma import get_chroma_client
from kognitmed.infrastructure.database.red_medica_store import RedMedicaSearchService
from kognitmed.infrastructure.llm_providers import build_llm_provider, build_llm_provider_for_layer
from kognitmed.infrastructure.memory.in_memory_store import InMemoryConversationStore


@lru_cache
def get_conversation_store() -> InMemoryConversationStore:
    return InMemoryConversationStore()


_red_medica_search_service: RedMedicaSearchService | None = None


def get_red_medica_search_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> RedMedicaSearchService:
    """Singleton: RedMedicaSearchService backed by ChromaDB (file mode)."""
    global _red_medica_search_service
    if _red_medica_search_service is None:
        chroma_client = get_chroma_client(settings)
        _red_medica_search_service = RedMedicaSearchService(chroma_client)
    return _red_medica_search_service


def get_chat_service(
    settings: Annotated[Settings, Depends(get_settings)],
    store: Annotated[InMemoryConversationStore, Depends(get_conversation_store)],
) -> ChatService:
    provider = build_llm_provider(settings)
    return ChatService(llm_provider=provider, memory_store=store, settings=settings)


def get_orientador_service(
    settings: Annotated[Settings, Depends(get_settings)],
    store: Annotated[InMemoryConversationStore, Depends(get_conversation_store)],
    search_service: Annotated[RedMedicaSearchService, Depends(get_red_medica_search_service)],
) -> MediOrientadorService:
    """Dependency for MediOrientadorService.

    Builds two independent LLM providers:
    - extraction_llm: fast/cheap model (gpt-4o-mini) for JSON symptom extraction.
    - synthesis_llm:  capable model (gpt-4o) for warm conversational responses.

    Injects RedMedicaSearchService to query the real hospital network from ChromaDB.
    """
    extraction_llm = build_llm_provider_for_layer(settings, layer="extraction")
    synthesis_llm = build_llm_provider_for_layer(settings, layer="synthesis")
    return MediOrientadorService(
        extraction_llm=extraction_llm,
        synthesis_llm=synthesis_llm,
        memory_store=store,
        settings=settings,
        search_service=search_service,
    )
