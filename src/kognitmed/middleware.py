"""Security middleware: CORS + secure HTTP headers.

TODO(security): Tighten ALLOWED_ORIGINS to production domain before deploy.
TODO(security): Add rate limiting middleware (e.g., slowapi) to protect /chat.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from kognitmed.config import Settings


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Adds security headers to every response."""

    async def dispatch(self, request: Request, call_next: object) -> Response:
        response: Response = await call_next(request)  # type: ignore[arg-type]
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self'; "
            "object-src 'none'; "
            "frame-ancestors 'none';"
        )
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(self)"
        return response


def register_middleware(app: FastAPI, settings: Settings) -> None:
    """Register all middleware on the FastAPI app."""
    # Security headers — must be outermost (added last, runs first)
    app.add_middleware(SecurityHeadersMiddleware)

    # CORS — never use wildcard origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST"],  # Only needed HTTP methods
        allow_headers=["Authorization", "Content-Type"],
    )
