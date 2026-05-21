"""FastAPI-mounted browser frontend for the KognitMed chatbot."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

WEB_ROOT = Path(__file__).with_name("web")


def mount_chat_frontend(app: FastAPI) -> None:
    """Expose the chatbot shell and its static browser assets."""
    app.mount(
        "/chat-assets",
        StaticFiles(directory=WEB_ROOT),
        name="chat-assets",
    )

    @app.get("/", include_in_schema=False)
    async def chat_frontend() -> FileResponse:
        return FileResponse(WEB_ROOT / "index.html")
