"""MediOrientador schemas — request/response contracts for the orientation service."""

from __future__ import annotations

from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from kognitmed.domain.models.orientador import (
    BenefitRecommendation,
    InsurancePlan,
    PatientContext,
    UrgencyLevel,
)


class OrientationRequest(BaseModel):
    """Mensaje del paciente hacia MediOrientador."""

    conversation_id: UUID = Field(
        default_factory=uuid4,
        description="ID de sesión. Enviar el mismo ID para continuar la conversación.",
    )
    message: str = Field(
        min_length=1,
        max_length=2048,
        description="Síntoma o consulta del paciente en lenguaje natural.",
    )
    patient_context: Optional[PatientContext] = Field(
        default=None,
        description="Contexto del paciente (plan de seguro, ubicación). "
                    "Si se omite, MediOrientador opera sin datos de cobertura.",
    )
    latitud: Optional[float] = Field(
        default=None,
        description="Latitud GPS del paciente (desde el navegador/frontend).",
    )
    longitud: Optional[float] = Field(
        default=None,
        description="Longitud GPS del paciente (desde el navegador/frontend).",
    )


class OrientationResponse(BaseModel):
    """Respuesta de MediOrientador al paciente."""

    conversation_id: UUID
    reply: str = Field(description="Respuesta conversacional para mostrar al paciente.")
    urgency: UrgencyLevel = UrgencyLevel.NORMAL
    recommendation: Optional[BenefitRecommendation] = Field(
        default=None,
        description="Recomendación estructurada (especialidad, copago, hospital). "
                    "None si el agente aún está recopilando información.",
    )
    provider: str
