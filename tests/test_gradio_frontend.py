"""Focused tests for the Gradio frontend API client."""

from __future__ import annotations

import json
from uuid import uuid4

import httpx
import pytest

from kognitmed.frontend.gradio_app import CHAT_PATH, _assistant_error, request_chat_response


@pytest.mark.asyncio
async def test_request_chat_response_sends_existing_conversation_id() -> None:
    conversation_id = uuid4()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == CHAT_PATH
        assert request.read()
        assert json.loads(request.content) == {
            "message": "Me duele la cabeza.",
            "conversation_id": str(conversation_id),
        }
        return httpx.Response(
            200,
            json={
                "conversation_id": str(conversation_id),
                "response": "Cuentame desde cuando.",
                "provider": "mock",
            },
        )

    reply, returned_id, provider = await request_chat_response(
        "Me duele la cabeza.",
        str(conversation_id),
        base_url="http://testserver",
        transport=httpx.MockTransport(handler),
    )

    assert reply == "Cuentame desde cuando."
    assert returned_id == str(conversation_id)
    assert provider == "mock"


def test_assistant_error_uses_backend_error_message() -> None:
    request = httpx.Request("POST", "http://testserver/api/v1/chat")
    response = httpx.Response(
        502,
        request=request,
        json={"error": {"code": "LLM_ERROR", "message": "AI service temporarily unavailable."}},
    )
    exc = httpx.HTTPStatusError("failed", request=request, response=response)

    assert _assistant_error(exc) == "El backend respondio: AI service temporarily unavailable."
