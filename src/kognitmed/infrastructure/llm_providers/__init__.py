"""LLM provider factory."""

from __future__ import annotations

from kognitmed.config import Settings
from kognitmed.infrastructure.llm_providers.base_provider import AbstractLLMProvider


def build_llm_provider(settings: Settings) -> AbstractLLMProvider:
    """Instantiate the configured LLM provider."""
    if settings.llm_provider == "openai":
        from kognitmed.infrastructure.llm_providers.openai_provider import OpenAIProvider
        return OpenAIProvider(api_key=settings.openai_api_key, model=settings.openai_model)
    elif settings.llm_provider == "gemini":
        from kognitmed.infrastructure.llm_providers.gemini_provider import GeminiProvider
        return GeminiProvider(api_key=settings.gemini_api_key, model=settings.gemini_model)
    else:
        raise ValueError(f"Unknown LLM provider: '{settings.llm_provider}'. Use 'openai' or 'gemini'.")
