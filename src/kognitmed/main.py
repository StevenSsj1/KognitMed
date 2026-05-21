"""
KognitMed FastAPI application factory.

create_app() is the single entry point for building the configured app.
This pattern makes the app easily testable and avoids module-level side effects.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
from fastapi import FastAPI
from pydantic import ValidationError

from kognitmed.config import get_settings
from kognitmed.domain.exceptions import DomainException, EntityNotFoundError, LLMProviderError
from kognitmed.exceptions import (
    domain_exception_handler,
    generic_error_handler,
    llm_error_handler,
    not_found_handler,
    validation_error_handler,
)
from kognitmed.infrastructure.api.router import root_router
from kognitmed.infrastructure.core.logging import configure_logging
from kognitmed.middleware import register_middleware

log = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup and shutdown lifecycle."""
    settings = get_settings()
    configure_logging(debug=settings.debug)
    log.info("kognitmed_starting", provider=settings.llm_provider, debug=settings.debug)

    # Initialize and verify MongoDB connection
    from kognitmed.infrastructure.database.mongo import ping_mongo, close_mongo_client
    db_connected = await ping_mongo(settings)
    if not db_connected:
        log.warning("database_connection_not_ready_at_startup")

    yield

    # Clean up database client connection
    close_mongo_client()
    log.info("kognitmed_shutdown")


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        description="Medical AI Agent API — powered by KognitMed",
        version="0.1.0",
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
        openapi_url="/openapi.json" if settings.debug else None,
        lifespan=lifespan,
    )

    # Middleware (order matters — last added runs first)
    register_middleware(app, settings)

    # Exception handlers
    app.add_exception_handler(EntityNotFoundError, not_found_handler)  # type: ignore[arg-type]
    app.add_exception_handler(LLMProviderError, llm_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(DomainException, domain_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(ValidationError, validation_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, generic_error_handler)

    # Routers
    app.include_router(root_router)

    return app


# Entrypoint for uvicorn
app = create_app()
