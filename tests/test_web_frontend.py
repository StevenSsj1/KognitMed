"""Focused tests for the browser chatbot shell."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_chat_frontend_is_served_by_fastapi(client: AsyncClient) -> None:
    response = await client.get("/")

    assert response.status_code == 200
    assert 'id="composer"' in response.text
    assert "/chat-assets/app.js" in response.text


@pytest.mark.asyncio
async def test_chat_frontend_script_stores_location(client: AsyncClient) -> None:
    response = await client.get("/chat-assets/app.js")

    assert response.status_code == 200
    assert 'const LOCATION_KEY = "kognitmed.location";' in response.text
    assert "navigator.geolocation.getCurrentPosition" in response.text
    assert "localStorage.setItem(LOCATION_KEY" in response.text


@pytest.mark.asyncio
async def test_chat_frontend_script_deletes_local_conversations(client: AsyncClient) -> None:
    response = await client.get("/chat-assets/app.js")

    assert response.status_code == 200
    assert "history-delete" in response.text
    assert "function deleteConversation(conversationId, row)" in response.text
    assert "state.conversations.length === 0" in response.text


@pytest.mark.asyncio
async def test_chat_frontend_css_respects_reduced_motion(client: AsyncClient) -> None:
    response = await client.get("/chat-assets/styles.css")

    assert response.status_code == 200
    assert "@media (prefers-reduced-motion: reduce)" in response.text
