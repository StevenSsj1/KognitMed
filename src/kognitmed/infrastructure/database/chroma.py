"""ChromaDB vector store connection helper — file/persistent mode.

Uses chromadb.PersistentClient: stores data locally on disk, no server needed.
Ideal for MVP and local development.

Only the connection is established here — no document ingestion logic.
"""

from __future__ import annotations

import structlog
import chromadb
from chromadb import ClientAPI
from kognitmed.config import Settings

log = structlog.get_logger(__name__)

_chroma_client: ClientAPI | None = None


def get_chroma_client(settings: Settings) -> ClientAPI:
    """Retrieve or initialize the global PersistentClient (file mode)."""
    global _chroma_client
    if _chroma_client is None:
        log.info("chroma_connecting", mode="persistent", path=settings.chroma_persist_path)
        _chroma_client = chromadb.PersistentClient(path=settings.chroma_persist_path)
    return _chroma_client


def close_chroma_client() -> None:
    """Release the global ChromaDB client reference."""
    global _chroma_client
    if _chroma_client is not None:
        log.info("chroma_connection_closing")
        _chroma_client = None


def ping_chroma(settings: Settings) -> bool:
    """Verify ChromaDB is accessible by calling heartbeat."""
    client = get_chroma_client(settings)
    try:
        client.heartbeat()
        log.info("chroma_connected", mode="persistent", path=settings.chroma_persist_path)
        return True
    except Exception as e:
        log.error("chroma_connection_failed", error=str(e))
        return False
