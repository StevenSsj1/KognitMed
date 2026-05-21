"""MediOrientador API endpoints — patient orientation interface."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from kognitmed.application.orientador_service.schemas import (
    OrientationRequest,
    OrientationResponse,
)
from kognitmed.application.orientador_service.service import MediOrientadorService
from kognitmed.dependencies import get_orientador_service

router = APIRouter(prefix="/orientador", tags=["orientador"])


@router.post(
    "",
    response_model=OrientationResponse,
    summary="Orientación médica: síntoma → especialidad → copago → hospital",
)
async def orient(
    request: OrientationRequest,
    service: Annotated[MediOrientadorService, Depends(get_orientador_service)],
) -> OrientationResponse:
    """
    Envía los síntomas del paciente a MediOrientador.

    MediOrientador:
    1. **Valida** el mensaje y detecta emergencias rápidamente.
    2. **Extrae** síntomas y sugiere especialidad médica via LLM.
    3. **Cruza** con el plan de seguro para calcular copago y hospital.
    4. **Responde** de forma conversacional y cálida.

    - Envía el mismo `conversation_id` para continuar la conversación.
    - Incluye `patient_context` con el plan de seguro para obtener copagos exactos.
    """
    return await service.orient(request)


@router.get(
    "/{conversation_id}/history",
    summary="Historial de la sesión de orientación",
)
async def get_history(
    conversation_id: UUID,
    service: Annotated[MediOrientadorService, Depends(get_orientador_service)],
) -> list[dict[str, str]]:
    """Recupera el historial completo de una sesión de orientación."""
    return await service.get_history(conversation_id)
