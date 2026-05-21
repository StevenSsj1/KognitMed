"""v1 API router aggregator."""

from fastapi import APIRouter

from kognitmed.infrastructure.api.v1 import chat, health, orientador

router = APIRouter()
router.include_router(health.router)
router.include_router(chat.router)
router.include_router(orientador.router)
