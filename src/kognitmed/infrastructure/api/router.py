"""Root API router."""

from fastapi import APIRouter

from kognitmed.config import get_settings
from kognitmed.infrastructure.api.v1.router import router as v1_router

settings = get_settings()

root_router = APIRouter()
root_router.include_router(v1_router, prefix=settings.api_v1_prefix)
