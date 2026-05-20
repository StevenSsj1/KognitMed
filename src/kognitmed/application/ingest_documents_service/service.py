"""Document ingestion service — prepares documents for future RAG pipeline."""

from __future__ import annotations

import structlog
from uuid import uuid4

log = structlog.get_logger(__name__)

# Simple in-memory document store (replace with vector DB for production RAG)
_document_store: list[dict[str, object]] = []


class IngestService:
    """
    Ingests text documents with basic chunking.

    Currently stores chunks in memory. This is designed to be swapped
    with a vector database + embeddings for full RAG capability.
    """

    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 50) -> None:
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap

    def ingest(self, text: str, metadata: dict[str, str] | None = None) -> list[str]:
        """
        Split text into overlapping chunks and store them.

        Args:
            text: Raw document text to ingest.
            metadata: Optional metadata (source, author, date, etc.)

        Returns:
            List of chunk IDs.
        """
        if not text.strip():
            return []

        chunks = self._chunk_text(text)
        chunk_ids: list[str] = []

        for chunk in chunks:
            chunk_id = str(uuid4())
            _document_store.append({
                "id": chunk_id,
                "content": chunk,
                "metadata": metadata or {},
            })
            chunk_ids.append(chunk_id)

        log.info("documents_ingested", chunk_count=len(chunks))
        return chunk_ids

    def _chunk_text(self, text: str) -> list[str]:
        """Split text into overlapping chunks."""
        chunks: list[str] = []
        start = 0
        while start < len(text):
            end = start + self._chunk_size
            chunks.append(text[start:end].strip())
            start += self._chunk_size - self._chunk_overlap
        return [c for c in chunks if c]

    def list_documents(self) -> list[dict[str, object]]:
        """Return all ingested document chunks."""
        return list(_document_store)
