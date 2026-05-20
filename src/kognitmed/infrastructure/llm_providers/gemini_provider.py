"""Google Gemini LLM provider implementation."""

from __future__ import annotations

import structlog
import google.generativeai as genai

from kognitmed.domain.exceptions import LLMProviderError
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
        genai.configure(api_key=api_key)
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
            model = genai.GenerativeModel(self._model_name)

            # Convert OpenAI-style messages to Gemini format
            # System messages are prepended to the first user message
            system_parts: list[str] = []
            chat_history = []
            pending_user: str | None = None

            for msg in messages:
                if msg["role"] == "system":
                    system_parts.append(msg["content"])
                elif msg["role"] == "user":
                    prefix = "\n".join(system_parts)
                    system_parts = []
                    pending_user = f"{prefix}\n\n{msg['content']}".strip() if prefix else msg["content"]
                elif msg["role"] == "assistant" and pending_user is not None:
                    chat_history.append({"role": "user", "parts": [pending_user]})
                    chat_history.append({"role": "model", "parts": [msg["content"]]})
                    pending_user = None

            chat = model.start_chat(history=chat_history)
            last_user = pending_user or ""
            response = await chat.send_message_async(last_user)
            return response.text
        except Exception as exc:
            log.error("gemini_completion_failed", error_type=type(exc).__name__)
            raise LLMProviderError("gemini", detail=type(exc).__name__) from exc
