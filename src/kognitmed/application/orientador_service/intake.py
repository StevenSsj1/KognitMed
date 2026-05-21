"""Layer 1 — Intake: validación y normalización del input del paciente.

Recibe el mensaje crudo del paciente y el contexto de su plan de seguro,
los valida, limpia y produce un IntakeResult listo para el matcher.
Este layer NO llama al LLM — es puro Python.
"""

from __future__ import annotations

import re
import structlog

from pydantic import BaseModel, Field

from kognitmed.domain.models.orientador import (
    InsurancePlan,
    PatientContext,
    UrgencyLevel,
)

log = structlog.get_logger(__name__)

# Palabras clave que disparan revisión de emergencia inmediata
_EMERGENCY_KEYWORDS: frozenset[str] = frozenset({
    "infarto", "paro", "paro cardíaco", "paro cardiaco",
    "no puedo respirar", "dificultad para respirar", "dificultad respirar",
    "pérdida de consciencia", "perdí el conocimiento", "perdi el conocimiento",
    "convulsión", "convulsion", "sangrado abundante", "hemorragia",
    "dolor en el pecho", "dolor pecho", "dolor torácico",
    "accidente cerebrovascular", "derrame cerebral", "stroke",
    "quemadura grave", "envenenamiento", "intoxicación",
})

# Longitud mínima/máxima razonable para un síntoma real
_MIN_MSG_LEN: int = 3
_MAX_MSG_LEN: int = 2048


class IntakeResult(BaseModel):
    """Resultado limpio y validado del paso de ingreso."""

    raw_message: str = Field(description="Mensaje original del paciente (sin modificar).")
    clean_message: str = Field(description="Mensaje normalizado (trim, unicode, etc.).")
    has_plan: bool = Field(description="True si el paciente viene con un plan de seguro cargado.")
    plan: InsurancePlan | None = Field(default=None)
    patient_context: PatientContext | None = Field(default=None)
    fast_emergency_flag: bool = Field(
        default=False,
        description="True si una keyword de emergencia fue detectada sin LLM.",
    )
    urgency_hint: UrgencyLevel = Field(
        default=UrgencyLevel.NORMAL,
        description="Pista de urgencia basada en heurísticas rápidas.",
    )
    validation_errors: list[str] = Field(default_factory=list)


class IntakeLayer:
    """
    Valida, limpia y pre-procesa el input del paciente.

    Responsabilidades:
    - Rechaza mensajes vacíos, demasiado cortos o demasiado largos.
    - Normaliza whitespace y caracteres especiales.
    - Detecta keywords de emergencia sin necesidad del LLM.
    - Expone el plan de seguro del paciente si está disponible.
    """

    def process(
        self,
        raw_message: str,
        patient_context: PatientContext | None = None,
    ) -> IntakeResult:
        """Valida y normaliza el input. Siempre retorna un IntakeResult (nunca lanza)."""
        errors: list[str] = []

        # ── Validaciones básicas ──────────────────────────────────────────────
        if not isinstance(raw_message, str):
            raw_message = str(raw_message)

        clean = self._normalize(raw_message)

        if len(clean) < _MIN_MSG_LEN:
            errors.append("El mensaje es demasiado corto para ser analizado.")
        if len(clean) > _MAX_MSG_LEN:
            errors.append(f"El mensaje supera el límite de {_MAX_MSG_LEN} caracteres.")
            clean = clean[:_MAX_MSG_LEN]

        # ── Detección rápida de emergencia (sin LLM) ──────────────────────────
        lower = clean.lower()
        fast_emergency = any(kw in lower for kw in _EMERGENCY_KEYWORDS)
        urgency_hint = UrgencyLevel.EMERGENCY if fast_emergency else UrgencyLevel.NORMAL

        # ── Plan de seguro ────────────────────────────────────────────────────
        plan = patient_context.plan if patient_context else None

        if errors:
            log.warning("intake_validation_errors", errors=errors)

        log.info(
            "intake_processed",
            msg_len=len(clean),
            has_plan=plan is not None,
            fast_emergency=fast_emergency,
        )

        return IntakeResult(
            raw_message=raw_message,
            clean_message=clean,
            has_plan=plan is not None,
            plan=plan,
            patient_context=patient_context,
            fast_emergency_flag=fast_emergency,
            urgency_hint=urgency_hint,
            validation_errors=errors,
        )

    # ── Helpers privados ──────────────────────────────────────────────────────

    @staticmethod
    def _normalize(text: str) -> str:
        """Normaliza whitespace y elimina caracteres de control."""
        # Eliminar caracteres de control (excepto \n)
        text = re.sub(r"[^\S\n]+", " ", text)
        # Colapsar múltiples saltos de línea
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()
