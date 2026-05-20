"""Test fixtures and configuration."""

from __future__ import annotations

from typing import AsyncGenerator
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from kognitmed.infrastructure.llm_providers.base_provider import AbstractLLMProvider
from kognitmed.main import create_app


class MockLLMProvider(AbstractLLMProvider):
    """Mock LLM provider for tests — no real API calls."""

    def __init__(self, response: str = "Mock medical response.") -> None:
        self._response = response

    @property
    def provider_name(self) -> str:
        return "mock"

    async def complete(self, messages: list[dict[str, str]], **kwargs: object) -> str:
        return self._response


@pytest.fixture
def mock_provider() -> MockLLMProvider:
    return MockLLMProvider()


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Async test client. Server binds to localhost (never 0.0.0.0)."""
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://localhost",  # MUST be localhost, not 0.0.0.0
    ) as ac:
        yield ac
