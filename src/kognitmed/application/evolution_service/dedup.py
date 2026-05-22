"""In-memory message deduplication with TTL."""

from __future__ import annotations

import time


class MessageDeduplicator:
    """Tracks seen message IDs to prevent reprocessing.

    Uses a simple dict with timestamps; entries older than ``ttl_seconds``
    are lazily evicted on each check.
    """

    def __init__(self, ttl_seconds: int = 3600) -> None:
        self._seen: dict[str, float] = {}
        self._ttl = ttl_seconds

    def is_duplicate(self, key: str) -> bool:
        """Return True if this key was already seen within the TTL window."""
        self._evict()
        if key in self._seen:
            return True
        self._seen[key] = time.monotonic()
        return False

    def _evict(self) -> None:
        cutoff = time.monotonic() - self._ttl
        expired = [k for k, ts in self._seen.items() if ts < cutoff]
        for k in expired:
            del self._seen[k]
