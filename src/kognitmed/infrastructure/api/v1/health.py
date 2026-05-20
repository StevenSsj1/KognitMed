"""Health check endpoints."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter

from kognitmed import __version__

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", summary="Liveness probe")
async def health() -> dict[str, object]:
    """Returns service status, useful for load balancers and monitoring."""
    return {
        "status": "ok",
        "version": __version__,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/ready", summary="Readiness probe")
async def ready() -> dict[str, str]:
    """Returns when the service is ready to handle requests."""
    return {"status": "ready"}
