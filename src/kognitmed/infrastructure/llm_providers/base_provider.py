"""Abstract LLM provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod


class AbstractLLMProvider(ABC):
    """Interface for all LLM provider implementations."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Identifier for this provider (e.g., 'openai', 'gemini')."""
        ...

    @abstractmethod
    async def complete(
        self,
        messages: list[dict[str, str]],
        **kwargs: object,
    ) -> str:
        """
        Send messages to the LLM and return the assistant's text response.

        Args:
            messages: List of {"role": ..., "content": ...} dicts.
            **kwargs: Provider-specific overrides (e.g., temperature, max_tokens).
        """
        ...
