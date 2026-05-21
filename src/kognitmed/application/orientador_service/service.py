"""MediOrientador — orchestrator service.

Orquesta los 3 layers del agente:
  Layer 1 (intake.py)  → valida y normaliza el input
  Layer 2 (matcher.py) → cruza síntomas con plan de seguro
  Layer 3 (output.py)  → sintetiza respuesta conversacional + estructura

No contiene lógica de negocio propia: delega en cada layer.
"""

from __future__ import annotations

import json
import structlog
from uuid import UUID

from kognitmed.application.orientador_service.intake import IntakeLayer, IntakeResult
from kognitmed.application.orientador_service.matcher import MatcherLayer
from kognitmed.application.orientador_service.output import OutputLayer
from kognitmed.application.orientador_service.schemas import (
    OrientationRequest,
    OrientationResponse,
)
from kognitmed.config import Settings
from kognitmed.domain.models.orientador import SymptomAnalysis, UrgencyLevel
from kognitmed.domain.prompts.orientador_prompts import SYMPTOM_INTENT_PROMPT
from kognitmed.infrastructure.llm_providers.base_provider import AbstractLLMProvider
from kognitmed.infrastructure.memory.in_memory_store import InMemoryConversationStore

log = structlog.get_logger(__name__)


class MediOrientadorService:
    """
    Agente conversacional de orientación médica y beneficios.

    Flujo:
        1. [Intake]   Valida y normaliza el mensaje del paciente.
        2. [LLM-ext]  Extrae síntomas e intención en JSON — modelo rápido/barato.
        3. [Matcher]  Cruza síntomas con plan de seguro (sin LLM).
        4. [LLM-syn]  Genera respuesta cálida — modelo potente/capaz.
    """

    def __init__(
        self,
        extraction_llm: AbstractLLMProvider,
        synthesis_llm: AbstractLLMProvider,
        memory_store: InMemoryConversationStore,
        settings: Settings,
    ) -> None:
        self._extraction_llm = extraction_llm   # Layer extracción: rápido/barato
        self._synthesis_llm = synthesis_llm     # Layer síntesis: potente/capaz
        self._memory = memory_store
        self._settings = settings

        # Instancias de los 3 layers
        self._intake = IntakeLayer()
        self._matcher = MatcherLayer()
        self._output = OutputLayer(llm_provider=synthesis_llm)

    # ── Punto de entrada ──────────────────────────────────────────────────────

    async def orient(self, request: OrientationRequest) -> OrientationResponse:
        """Procesa el mensaje del paciente y retorna orientación médica + beneficios."""
        cid = request.conversation_id

        # Persistir mensaje del paciente en memoria
        await self._memory.add_message(
            conversation_id=cid, role="user", content=request.message
        )

        log.info("orientador_start", conversation_id=str(cid), provider=self._llm.provider_name)

        # ── Layer 1: Intake ───────────────────────────────────────────────────
        intake: IntakeResult = self._intake.process(
            raw_message=request.message,
            patient_context=request.patient_context,
        )

        if intake.validation_errors:
            # Mensaje inválido → responder con el primer error
            error_reply = f"No pude procesar tu consulta: {intake.validation_errors[0]}"
            await self._memory.add_message(conversation_id=cid, role="assistant", content=error_reply)
            return OrientationResponse(
                conversation_id=cid,
                reply=error_reply,
                urgency=UrgencyLevel.NORMAL,
                recommendation=None,
                provider=self._llm.provider_name,
            )

        # Cortocircuito de emergencia detectado por el intake (sin LLM)
        if intake.fast_emergency_flag:
            from kognitmed.application.orientador_service.output import _EMERGENCY_REPLY
            await self._memory.add_message(
                conversation_id=cid, role="assistant", content=_EMERGENCY_REPLY
            )
            log.warning("orientador_fast_emergency", conversation_id=str(cid))
            return OrientationResponse(
                conversation_id=cid,
                reply=_EMERGENCY_REPLY,
                urgency=UrgencyLevel.EMERGENCY,
                recommendation=None,
                provider=self._llm.provider_name,
            )

        # ── LLM: Extracción de síntomas (entre Layer 1 y 2) ──────────────────
        analysis: SymptomAnalysis = await self._extract_symptoms(intake.clean_message)

        # ── Layer 2: Matcher ──────────────────────────────────────────────────
        match = self._matcher.match(intake=intake, analysis=analysis)

        # ── Layer 3: Output ───────────────────────────────────────────────────
        history = await self._memory.get_history(cid)
        patient_ctx_str, insurance_ctx_str = self._build_context_strings(intake)

        response = await self._output.build_response(
            conversation_id=cid,
            match=match,
            history=history[:-1],  # excluir el mensaje actual ya procesado
            patient_context_str=patient_ctx_str,
            insurance_context_str=insurance_ctx_str,
        )

        # Persistir respuesta del agente
        await self._memory.add_message(
            conversation_id=cid, role="assistant", content=response.reply
        )

        log.info("orientador_done", conversation_id=str(cid))
        return response

    async def get_history(self, conversation_id: UUID) -> list[dict[str, str]]:
        """Devuelve el historial de la conversación."""
        return await self._memory.get_history(conversation_id)

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _extract_symptoms(self, clean_message: str) -> SymptomAnalysis:
        """Llama al LLM de extracción (rápido/barato) para obtener JSON estructurado."""
        prompt = SYMPTOM_INTENT_PROMPT.render(patient_message=clean_message)
        raw = await self._extraction_llm.complete(
            [{"role": "user", "content": prompt}], temperature=0.0
        )

        try:
            cleaned = (
                raw.strip()
                .removeprefix("```json")
                .removeprefix("```")
                .removesuffix("```")
                .strip()
            )
            data = json.loads(cleaned)
            return SymptomAnalysis(
                symptoms=data.get("symptoms", []),
                suggested_specialties=data.get("suggested_specialties", []),
                urgency=UrgencyLevel(data.get("urgency", "normal")),
                is_emergency=bool(data.get("is_emergency", False)),
                reasoning=data.get("reasoning", ""),
            )
        except (ValueError, KeyError) as exc:
            log.warning("orientador_symptom_parse_error", error=str(exc), raw=raw[:200])
            return SymptomAnalysis(
                symptoms=[clean_message[:120]],
                suggested_specialties=["Medicina General"],
                urgency=UrgencyLevel.NORMAL,
                is_emergency=False,
                reasoning="Análisis estructurado no disponible — fallback a Medicina General.",
            )

    def _build_context_strings(self, intake: IntakeResult) -> tuple[str, str]:
        """Construye las cadenas de contexto para los prompts del output layer."""
        patient_ctx_str = "No se cargaron datos del paciente."
        insurance_ctx_str = "No se encontró un plan de seguro activo."

        if intake.patient_context:
            loc = intake.patient_context.preferred_location or "No especificada"
            patient_ctx_str = f"Ubicación preferida: {loc}."

        if intake.plan:
            plan = intake.plan
            specialties_str = ", ".join(plan.covered_specialties) or "No especificadas"
            insurance_ctx_str = (
                f"Plan: {plan.plan_name} — {plan.insurer}. "
                f"Especialidades cubiertas: {specialties_str}."
            )

        return patient_ctx_str, insurance_ctx_str
