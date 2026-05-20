"""Global FastAPI exception handlers.

User-facing messages are intentionally generic to avoid leaking internals.
Detailed diagnostics are logged server-side only.
"""

from __future__ import annotations

import structlog
from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from kognitmed.domain.exceptions import (
    DomainException,
    EntityNotFoundError,
    LLMProviderError,
)

log = structlog.get_logger(__name__)


async def domain_exception_handler(request: Request, exc: DomainException) -> JSONResponse:
    log.warning("domain_error", code=exc.code, path=str(request.url))
    return JSONResponse(
        status_code=400,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


async def not_found_handler(request: Request, exc: EntityNotFoundError) -> JSONResponse:
    log.info("not_found", entity=exc.entity, entity_id=exc.entity_id, path=str(request.url))
    return JSONResponse(
        status_code=404,
        content={"error": {"code": "NOT_FOUND", "message": exc.message}},
    )


async def llm_error_handler(request: Request, exc: LLMProviderError) -> JSONResponse:
    # Do NOT expose the provider detail in the user response
    log.error("llm_provider_error", provider=exc.provider, path=str(request.url))
    return JSONResponse(
        status_code=502,
        content={"error": {"code": "LLM_ERROR", "message": "AI service temporarily unavailable."}},
    )


async def validation_error_handler(request: Request, exc: ValidationError) -> JSONResponse:
    log.info("validation_error", path=str(request.url), errors=exc.error_count())
    return JSONResponse(
        status_code=422,
        content={"error": {"code": "VALIDATION_ERROR", "message": "Invalid request data."}},
    )


async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
    # Generic error — details logged internally, never exposed
    log.exception("unhandled_error", path=str(request.url))
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "INTERNAL_ERROR", "message": "An unexpected error occurred."}},
    )
