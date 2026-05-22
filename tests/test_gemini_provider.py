"""Focused tests for the Google GenAI Gemini provider adapter."""

from __future__ import annotations

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
