"""Layer 3 — Output: formatea la respuesta final para el paciente.

Recibe el MatchResult del Layer 2 y genera:
  - Una respuesta conversacional cálida via LLM.
  - Un OrientationResponse estructurado con todos los datos.

Es el único layer que vuelve a tocar el LLM (para la síntesis narrativa).
"""

from __future__ import annotations

import structlog

from kognitmed.application.orientador_service.matcher import MatchResult
from kognitmed.application.orientador_service.schemas import OrientationResponse
from kognitmed.domain.models.orientador import UrgencyLevel
from kognitmed.domain.prompts.orientador_prompts import (
    BENEFIT_SYNTHESIS_PROMPT,
    MEDIO_ORIENTADOR_SYSTEM_PROMPT,
)
from kognitmed.infrastructure.llm_providers.base_provider import AbstractLLMProvider

log = structlog.get_logger(__name__)

# ── Respuestas hardcoded para emergencias (no pasan por LLM) ──────────────────

_EMERGENCY_REPLY = (
    "⚠️ **Atención: situación de emergencia detectada.**\n\n"
    "Los síntomas que describes requieren atención médica inmediata. "
    "Por favor, **llama al 911** o acude ahora mismo a la sala de emergencias "
    "más cercana.\n\n"
    "No esperes ni intentes manejar esto por tu cuenta. Puedes hablar conmigo "
    "después para orientarte sobre tu cobertura y copagos. 🏥"
)

_NO_PLAN_GUIDANCE = (
    "Para darte información exacta de copagos y hospitales en red, "
    "necesito los datos de tu plan de seguro. Puedes agregarlos al inicio "
    "de la sesión o llamar directamente al número en tu tarjeta de seguro."
)


class OutputLayer:
    """
    Layer 3: síntesis narrativa y construcción del OrientationResponse.

    Responsabilidades:
    - Cortocircuito para emergencias (sin LLM).
    - Llamada al LLM para generar respuesta conversacional cálida.
    - Ensambla el OrientationResponse final con datos estructurados.
    """

    def __init__(self, llm_provider: AbstractLLMProvider) -> None:
        self._llm = llm_provider

    async def build_response(
        self,
        *,
        conversation_id,
        match: MatchResult,
        history: list[dict[str, str]],
        patient_context_str: str = "",
        insurance_context_str: str = "",
    ) -> OrientationResponse:
        """Genera el OrientationResponse final."""

        from kognitmed.application.orientador_service.schemas import OrientationResponse
        from kognitmed.application.orientador_service.matcher import MatcherLayer

        # ── Cortocircuito emergencia ──────────────────────────────────────────
        if match.urgency == UrgencyLevel.EMERGENCY:
            log.warning("output_emergency_shortcircuit")
            return OrientationResponse(
                conversation_id=conversation_id,
                reply=_EMERGENCY_REPLY,
                urgency=UrgencyLevel.EMERGENCY,
                recommendation=None,
                provider=self._llm.provider_name,
            )

        # ── Construir BenefitRecommendation ───────────────────────────────────
        matcher_layer = MatcherLayer()
        recommendation = matcher_layer.to_benefit_recommendation(match)

        # ── Síntesis narrativa via LLM ────────────────────────────────────────
        reply = await self._synthesize(
            match=match,
            history=history,
            patient_context_str=patient_context_str or "No disponible.",
            insurance_context_str=insurance_context_str or "No disponible.",
        )

        # Actualiza el summary de la recomendación con la síntesis
        recommendation.summary = reply

        log.info(
            "output_response_built",
            specialty=match.chosen_specialty,
            is_covered=match.is_covered,
            urgency=match.urgency.value,
        )

        return OrientationResponse(
            conversation_id=conversation_id,
            reply=reply,
            urgency=match.urgency,
            recommendation=recommendation,
            provider=self._llm.provider_name,
        )

    # ── Síntesis privada ──────────────────────────────────────────────────────

    async def _synthesize(
        self,
        *,
        match: MatchResult,
        history: list[dict[str, str]],
        patient_context_str: str,
        insurance_context_str: str,
    ) -> str:
        """Llama al LLM para generar la respuesta conversacional cálida."""

        # Datos estructurados del match para el prompt
        top_hospital = match.hospitals[0].name if match.hospitals else "ninguno disponible en red"
        copago_str = f"${match.copay_usd:.2f}" if match.copay_usd is not None else "no determinado"

        analysis_data = (
            f"Especialidad recomendada: {match.chosen_specialty}. "
            f"Urgencia: {match.urgency.value}. "
            f"Nota de cobertura: {match.coverage_note}"
        )

        insurance_data: str
        if match.no_plan_available:
            insurance_data = _NO_PLAN_GUIDANCE
        else:
            insurance_data = (
                f"Cubierta: {'Sí' if match.is_covered else 'No'}. "
                f"Copago estimado: {copago_str}. "
                f"Hospital más conveniente: {top_hospital}."
            )

        synthesis_prompt = BENEFIT_SYNTHESIS_PROMPT.render(
            analysis_data=analysis_data,
            insurance_data=insurance_data,
        )

        system_prompt = MEDIO_ORIENTADOR_SYSTEM_PROMPT.render(
            patient_context=patient_context_str,
            insurance_context=insurance_context_str,
        )

        messages: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt},
            *history,
            {"role": "user", "content": synthesis_prompt},
        ]

        return (await self._llm.complete(messages, temperature=0.3)).strip()
