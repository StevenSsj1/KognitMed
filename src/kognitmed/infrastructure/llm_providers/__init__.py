"""LLM provider factory."""

from __future__ import annotations

from typing import Literal

from kognitmed.config import Settings
from kognitmed.infrastructure.llm_providers.base_provider import AbstractLLMProvider


def build_llm_provider(
    settings: Settings,
    model_override: str | None = None,
) -> AbstractLLMProvider:
    """Instantiate the configured LLM provider.

    Args:
        settings: Application settings.
        model_override: If provided, overrides the model defined in settings.
                        Useful for per-layer model selection.
    """
    if settings.llm_provider == "openai":
        from kognitmed.infrastructure.llm_providers.openai_provider import OpenAIProvider
        model = model_override or settings.openai_model
        return OpenAIProvider(api_key=settings.openai_api_key, model=model)
    elif settings.llm_provider == "gemini":
        from kognitmed.infrastructure.llm_providers.gemini_provider import GeminiProvider
        model = model_override or settings.gemini_model
        return GeminiProvider(api_key=settings.gemini_api_key, model=model)
    else:
        raise ValueError(f"Unknown LLM provider: '{settings.llm_provider}'. Use 'openai' or 'gemini'.")


def build_llm_provider_for_layer(
    settings: Settings,
    layer: Literal["extraction", "synthesis"],
) -> AbstractLLMProvider:
    """Build a provider with the model configured for a specific orientador layer.

    - ``extraction``: used between Layer 1→2, structured JSON task → fast/cheap model.
    - ``synthesis``:  used in Layer 3, conversational response → capable model.

    Falls back to the global model if the layer-specific override is empty.
    """
    overrides: dict[str, str] = {
        "extraction": settings.orientador_extraction_model,
        "synthesis": settings.orientador_synthesis_model,
    }
    model_override = overrides.get(layer) or None   # empty string → None → global fallback
    return build_llm_provider(settings, model_override=model_override)
