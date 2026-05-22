"""Google Gemini LLM provider implementation."""

from __future__ import annotations

import structlog
from google import genai
from google.genai import types

from kognitmed.domain.exceptions import (
    LLMNotConfiguredError,
    LLMProviderError,
    LLMRateLimitError,
)
from kognitmed.infrastructure.llm_providers.base_provider import AbstractLLMProvider

log = structlog.get_logger(__name__)


class GeminiProvider(AbstractLLMProvider):
    """Async Google Gemini provider."""

    def __init__(self, api_key: str, model: str) -> None:
        if not api_key:
            raise ValueError(
                "GEMINI_API_KEY is not set. "
                "Add it to your .env file or environment variables."
            )
        self._client = genai.Client(api_key=api_key)
        self._model_name = model

    @property
    def provider_name(self) -> str:
        return "gemini"

    async def complete(
        self,
        messages: list[dict[str, str]],
        **kwargs: object,
    ) -> str:
        try:
            # Separate system instruction from conversation
            system_parts: list[str] = []
            contents: list[types.Content] = []
            pending_user: str | None = None

            for msg in messages:
                if msg["role"] == "system":
                    system_parts.append(msg["content"])
                elif msg["role"] == "user":
                    prefix = "\n".join(system_parts)
                    system_parts = []
                    pending_user = f"{prefix}\n\n{msg['content']}".strip() if prefix else msg["content"]
                elif msg["role"] == "assistant" and pending_user is not None:
                    contents.append(types.Content(role="user", parts=[types.Part(text=pending_user)]))
                    contents.append(types.Content(role="model", parts=[types.Part(text=msg["content"])]))
                    pending_user = None

            # Add final user message
            if pending_user:
                contents.append(types.Content(role="user", parts=[types.Part(text=pending_user)]))

            response = await self._client.aio.models.generate_content(
                model=self._model_name,
                contents=contents,
            )
            return response.text
        except Exception as exc:
            detail = str(exc).strip() or type(exc).__name__
            log.error(
                "gemini_completion_failed",
                error_type=type(exc).__name__,
                error_detail=detail,
            )
            raise LLMProviderError("gemini", detail=detail) from exc

    @staticmethod
    def _build_contents(
        messages: list[dict[str, str]],
    ) -> tuple[str, list[types.Content]]:
        """Convert OpenAI-style chat messages to Google GenAI request contents."""
        system_parts: list[str] = []
        contents: list[types.Content] = []

        for message in messages:
            role = message["role"]
            if role == "system":
                system_parts.append(message["content"])
                continue
            if role not in {"user", "assistant"}:
                continue

            contents.append(
                types.Content(
                    role="model" if role == "assistant" else "user",
                    parts=[types.Part.from_text(text=message["content"])],
                )
            )

        return "\n\n".join(system_parts), contents
