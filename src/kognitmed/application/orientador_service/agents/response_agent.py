"""Layer 3 agent (response synthesis): final patient-facing answer and structured payload."""

from __future__ import annotations

import structlog

from kognitmed.application.orientador_service.agents.reasoning_agent import MatchResult, ReasoningAgent
from kognitmed.application.orientador_service.schemas import OrientationResponse
from kognitmed.domain.models.orientador import UrgencyLevel
from kognitmed.domain.prompts.orientador_prompts import (
    BENEFIT_SYNTHESIS_PROMPT,
    MEDIO_ORIENTADOR_SYSTEM_PROMPT,
)
from kognitmed.infrastructure.llm_providers.base_provider import AbstractLLMProvider

log = structlog.get_logger(__name__)

_EMERGENCY_REPLY = (
    "Atencion: los sintomas que describes pueden indicar una emergencia. "
    "Llama ahora al 911 o acude de inmediato a la sala de emergencias mas cercana. "
    "No retrases la atencion."
)

_NO_PLAN_GUIDANCE = (
    "Para darte copagos exactos y hospitales en red, necesito los datos de tu plan de seguro. "
    "Si no los tienes ahora, llama al numero de atencion de tu aseguradora."
)


class OutputAgent:
    """Compose the final answer using the match result and conversational context."""

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
        if match.urgency == UrgencyLevel.EMERGENCY:
            log.warning("output_emergency_shortcircuit")
            return OrientationResponse(
                conversation_id=conversation_id,
                reply=_EMERGENCY_REPLY,
                urgency=UrgencyLevel.EMERGENCY,
                recommendation=None,
                provider=self._llm.provider_name,
            )

        recommendation = ReasoningAgent.to_benefit_recommendation(match)

        reply = await self._synthesize(
            match=match,
            history=history,
            patient_context_str=patient_context_str or "No disponible.",
            insurance_context_str=insurance_context_str or "No disponible.",
        )
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

    async def _synthesize(
        self,
        *,
        match: MatchResult,
        history: list[dict[str, str]],
        patient_context_str: str,
        insurance_context_str: str,
    ) -> str:
        hospitals = [h.name for h in match.hospitals[:3]]
        hospitals_str = ", ".join(hospitals) if hospitals else "sin centros sugeridos"
        copay_str = f"${match.copay_usd:.2f}" if match.copay_usd is not None else "no determinado"

        analysis_data = (
            f"Especialidad recomendada: {match.chosen_specialty}. "
            f"Urgencia: {match.urgency.value}. "
            f"Detalle de cobertura: {match.coverage_note}."
        )

        if match.no_plan_available:
            insurance_data = _NO_PLAN_GUIDANCE
        else:
            insurance_data = (
                f"Cobertura: {'si' if match.is_covered else 'no'}. "
                f"Copago estimado base: {copay_str}. "
                f"Centros sugeridos: {hospitals_str}."
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

        return (await self._llm.complete(messages, temperature=0.2)).strip()
