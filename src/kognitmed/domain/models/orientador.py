"""Domain models for the MediOrientador agent.

Models the patient context, insurance plan, and the structured
output of the symptom intent extraction step.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


# ── Enumeraciones de dominio ──────────────────────────────────────────────────

class UrgencyLevel(str, Enum):
    """Nivel de urgencia determinado por el análisis de síntomas."""
    EMERGENCY = "emergencia"
    URGENT = "urgente"
    NORMAL = "normal"
    PREVENTIVE = "preventivo"


# ── Contexto del paciente ─────────────────────────────────────────────────────

class InsurancePlan(BaseModel):
    """Plan de seguro activo del paciente (simplificado para MVP)."""

    plan_name: str = Field(description="Nombre comercial del plan.")
    insurer: str = Field(description="Nombre de la aseguradora.")
    # Copagos por especialidad: {"Cardiología": 25.0, "Medicina General": 10.0}
    copay_by_specialty: dict[str, float] = Field(
        default_factory=dict,
        description="Copago en USD por especialidad médica.",
    )
    # Hospitales en red: [{"name": "Hospital X", "copay_modifier": 0.0}]
    network_hospitals: list[dict[str, object]] = Field(
        default_factory=list,
        description="Hospitales/clínicas en red con su modificador de copago.",
    )
    covered_specialties: list[str] = Field(
        default_factory=list,
        description="Lista de especialidades cubiertas por el plan.",
    )
    emergency_covered: bool = Field(
        default=True,
        description="Si las emergencias están cubiertas por el plan.",
    )


class PatientContext(BaseModel):
    """Datos del paciente disponibles en la sesión (sin PII sensible)."""

    patient_id: UUID = Field(default_factory=uuid4)
    plan: Optional[InsurancePlan] = Field(
        default=None,
        description="Plan de seguro activo. None si no se ha cargado.",
    )
    preferred_location: Optional[str] = Field(
        default=None,
        description="Ciudad o zona preferida del paciente.",
    )


# ── Resultado del análisis de síntomas ───────────────────────────────────────

class SymptomAnalysis(BaseModel):
    """Resultado estructurado del paso de extracción de intención."""

    symptoms: list[str] = Field(description="Síntomas detectados, normalizados.")
    suggested_specialties: list[str] = Field(
        description="Especialidades médicas sugeridas, ordenadas por relevancia."
    )
    urgency: UrgencyLevel = Field(description="Nivel de urgencia estimado.")
    is_emergency: bool = Field(
        default=False,
        description="True si el agente debe redirigir a emergencias inmediatamente.",
    )
    reasoning: str = Field(
        default="",
        description="Breve explicación del análisis.",
    )


# ── Recomendación de beneficio ────────────────────────────────────────────────

class HospitalRecommendation(BaseModel):
    """Hospital recomendado con copago calculado y datos enriquecidos desde la red médica."""

    name: str
    copay_usd: float
    is_in_network: bool
    notes: Optional[str] = None
    # Datos enriquecidos desde ChromaDB (red médica real)
    ciudad: Optional[str] = None
    aseguradoras: list[str] = Field(default_factory=list)
    especialidades: list[str] = Field(default_factory=list)
    latitud: Optional[float] = None
    longitud: Optional[float] = None
    relevance_score: Optional[float] = None


class BenefitRecommendation(BaseModel):
    """Resultado completo de la orientación: especialidad + copago + hospital."""

    recommended_specialty: str
    is_covered: bool
    estimated_copay_usd: Optional[float] = None
    hospitals: list[HospitalRecommendation] = Field(default_factory=list)
    summary: str = Field(description="Respuesta narrativa para el paciente.")
    urgency: UrgencyLevel = UrgencyLevel.NORMAL
