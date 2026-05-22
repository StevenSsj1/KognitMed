"""Focused tests for the Google GenAI Gemini provider adapter."""

from __future__ import annotations

import pytest

from kognitmed.infrastructure.llm_providers.gemini_provider import GeminiProvider


def test_gemini_provider_builds_system_instruction_and_chat_contents() -> None:
    system_instruction, contents = GeminiProvider._build_contents(
        [
            {"role": "system", "content": "Medical safety rules."},
            {"role": "user", "content": "Tengo dolor de cabeza."},
            {"role": "assistant", "content": "Desde cuando?"},
            {"role": "user", "content": "Desde ayer."},
        ]
    )

    assert system_instruction == "Medical safety rules."
    assert [content.role for content in contents] == ["user", "model", "user"]
    assert [content.parts[0].text for content in contents] == [
        "Tengo dolor de cabeza.",
        "Desde cuando?",
        "Desde ayer.",
    ]


@pytest.mark.asyncio
async def test_gemini_provider_rate_limit_error() -> None:
    from unittest.mock import AsyncMock, MagicMock
    from google.genai.errors import APIError
    from kognitmed.domain.exceptions import LLMRateLimitError

    provider = GeminiProvider(api_key="dummy_key", model="gemini-2.5-flash-lite")
    api_error = APIError(
        code=429,
        response_json={"error": {"code": 429, "message": "Quota exceeded"}},
    )

    # Mock the client's generate_content call
    provider._client = MagicMock()
    provider._client.aio = MagicMock()
    provider._client.aio.models = MagicMock()
    provider._client.aio.models.generate_content = AsyncMock(side_effect=api_error)

    with pytest.raises(LLMRateLimitError) as exc_info:
        await provider.complete([{"role": "user", "content": "hello"}])

    assert exc_info.value.code == "LLM_RATE_LIMITED"
    assert "Quota exceeded" in exc_info.value.detail
