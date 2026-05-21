"""Chat endpoint and ChatService tests."""

from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

import pytest
from httpx import AsyncClient

from kognitmed.application.chat_service.service import ChatService
from kognitmed.config import get_settings
from kognitmed.dependencies import get_chat_service
from kognitmed.infrastructure.memory.in_memory_store import InMemoryConversationStore
from kognitmed.infrastructure.llm_providers import build_llm_provider
from tests.conftest import MockLLMProvider


@pytest.mark.asyncio
async def test_chat_returns_response(client: AsyncClient) -> None:
    """POST /chat should return a valid response from the mock LLM."""
    mock = MockLLMProvider(response="Based on your symptoms, consider consulting a neurologist.")

    from kognitmed.main import create_app
    from kognitmed.config import get_settings

    app = create_app()
    store = InMemoryConversationStore()
    settings = get_settings()

    app.dependency_overrides[get_chat_service] = lambda: ChatService(
        llm_provider=mock,
        memory_store=store,
        settings=settings,
    )

    from httpx import ASGITransport, AsyncClient as AC
    async with AC(transport=ASGITransport(app=app), base_url="http://localhost") as c:
        response = await c.post(
            "/api/v1/chat",
            json={"message": "I have a headache and dizziness."},
        )

    assert response.status_code == 200
    data = response.json()
    assert "response" in data
    assert "conversation_id" in data
    assert data["provider"] == "mock"


@pytest.mark.asyncio
async def test_chat_maintains_history() -> None:
    """Messages should be persisted across calls in the same conversation."""
    provider = MockLLMProvider(response="I understand. Can you describe the pain?")
    store = InMemoryConversationStore()
    from kognitmed.config import get_settings
    service = ChatService(llm_provider=provider, memory_store=store, settings=get_settings())

    conv_id = uuid4()
    from kognitmed.application.chat_service.schemas import ChatRequest

    await service.chat(ChatRequest(conversation_id=conv_id, message="Hello"))
    await service.chat(ChatRequest(conversation_id=conv_id, message="I have a headache"))

    history = await service.get_history(conv_id)
    roles = [m["role"] for m in history]

    assert roles.count("user") == 2
    assert roles.count("assistant") == 2


@pytest.mark.asyncio
async def test_chat_empty_message_rejected(client: AsyncClient) -> None:
    """Empty messages should be rejected with 422."""
    response = await client.post("/api/v1/chat", json={"message": ""})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_chat_missing_llm_key_returns_configuration_error(client: AsyncClient) -> None:
    """Missing provider credentials should not leak as an internal server error."""
    settings = get_settings().model_copy(update={"llm_provider": "openai", "openai_api_key": ""})
    app = client._transport.app  # type: ignore[attr-defined]
    app.dependency_overrides[get_chat_service] = lambda: ChatService(
        llm_provider=build_llm_provider(settings),
        memory_store=InMemoryConversationStore(),
        settings=settings,
    )

    response = await client.post("/api/v1/chat", json={"message": "Tengo mareo."})

    assert response.status_code == 503
    assert response.json()["error"] == {
        "code": "LLM_NOT_CONFIGURED",
        "message": "El proveedor LLM no esta configurado. Define OPENAI_API_KEY.",
    }
