"""OpenAI LLM provider implementation."""

from __future__ import annotations

import structlog
from openai import AsyncOpenAI

from kognitmed.domain.exceptions import LLMNotConfiguredError, LLMProviderError
from kognitmed.infrastructure.llm_providers.base_provider import AbstractLLMProvider

log = structlog.get_logger(__name__)


class OpenAIProvider(AbstractLLMProvider):
    """Async OpenAI / GPT provider."""

    def __init__(self, api_key: str, model: str) -> None:
        if not api_key:
            raise LLMNotConfiguredError("openai", env_var="OPENAI_API_KEY")
        # API key is passed directly — never logged or stored in plaintext beyond this init
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model

    @property
    def provider_name(self) -> str:
        return "openai"

    async def complete(
        self,
        messages: list[dict[str, str]],
        **kwargs: object,
    ) -> str:
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,  # type: ignore[arg-type]
                temperature=kwargs.get("temperature", 0.3),  # type: ignore[arg-type]
                max_tokens=kwargs.get("max_tokens", 2048),  # type: ignore[arg-type]
            )
            content = response.choices[0].message.content
            return content or ""
        except Exception as exc:
            detail = str(exc).strip() or type(exc).__name__
            log.error(
                "openai_completion_failed",
                error_type=type(exc).__name__,
                error_detail=detail,
            )
            raise LLMProviderError("openai", detail=detail) from exc
