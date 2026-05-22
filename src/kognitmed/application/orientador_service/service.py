"""MediOrientador — orchestrator service.

Orquesta los 3 layers del agente:
  Layer 1 (agents/intake_agent.py)    → valida y normaliza el input
  Layer 2 (agents/reasoning_agent.py) → cruza síntomas con plan de seguro + ChromaDB
  Layer 3 (agents/response_agent.py)  → sintetiza respuesta conversacional + estructura

No contiene lógica de negocio propia: delega en cada layer.
"""

from __future__ import annotations

import json
import structlog
from uuid import UUID

from kognitmed.application.orientador_service.agents.intake_agent import IntakeAgent, IntakeResult
from kognitmed.application.orientador_service.agents.reasoning_agent import ReasoningAgent
from kognitmed.application.orientador_service.agents.response_agent import OutputAgent
from kognitmed.application.orientador_service.schemas import (
    OrientationRequest,
    OrientationResponse,
)
from kognitmed.config import Settings
from kognitmed.domain.models.orientador import SymptomAnalysis, UrgencyLevel
from kognitmed.domain.prompts.orientador_prompts import SYMPTOM_INTENT_PROMPT
from kognitmed.infrastructure.database.red_medica_store import RedMedicaSearchService
from kognitmed.infrastructure.llm_providers.base_provider import AbstractLLMProvider
from kognitmed.infrastructure.memory.in_memory_store import InMemoryConversationStore

log = structlog.get_logger(__name__)

_IDENTITY_REQUEST_REPLY = (
    "Antes de continuar con consultas laborales necesito validar tus datos. "
    "Por favor compárteme tu cédula y el nombre con el que deseas que te llame."
)


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
        search_service: RedMedicaSearchService | None = None,
    ) -> None:
        self._extraction_llm = extraction_llm   # Layer extracción: rápido/barato
        self._synthesis_llm = synthesis_llm     # Layer síntesis: potente/capaz
        self._memory = memory_store
        self._settings = settings
        self._search_service = search_service   # Red médica en ChromaDB

        # Instancias de los 3 layers
        self._intake = IntakeAgent()
        self._reasoning = ReasoningAgent()
        self._output = OutputAgent(llm_provider=synthesis_llm)

    # ── Punto de entrada ──────────────────────────────────────────────────────

    async def orient(self, request: OrientationRequest) -> OrientationResponse:
        """Procesa el mensaje del paciente y retorna orientación médica + beneficios."""
        cid = request.conversation_id

        # Persistir mensaje del paciente en memoria
        await self._memory.add_message(
            conversation_id=cid, role="user", content=request.message
        )
        history = await self._memory.get_history(cid)

        log.info("orientador_start", conversation_id=str(cid), provider=self._extraction_llm.provider_name)

        # ── Layer 1: Intake ───────────────────────────────────────────────────
        intake: IntakeResult = self._intake.process(
            raw_message=request.message,
            patient_context=request.patient_context,
            history=history,
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
                provider=self._extraction_llm.provider_name,
            )

        if intake.is_work_related and intake.missing_identity_fields:
            missing_spanish = ", ".join(intake.missing_identity_fields)
            reply = (
                f"{_IDENTITY_REQUEST_REPLY} "
                f"Datos faltantes detectados: {missing_spanish}."
            )
            await self._memory.add_message(conversation_id=cid, role="assistant", content=reply)
            return OrientationResponse(
                conversation_id=cid,
                reply=reply,
                urgency=UrgencyLevel.NORMAL,
                recommendation=None,
                provider=self._extraction_llm.provider_name,
            )

        # Cortocircuito de emergencia detectado por el intake (sin LLM)
        if intake.fast_emergency_flag:
            from kognitmed.application.orientador_service.agents.response_agent import _EMERGENCY_REPLY
            await self._memory.add_message(
                conversation_id=cid, role="assistant", content=_EMERGENCY_REPLY
            )
            log.warning("orientador_fast_emergency", conversation_id=str(cid))
            return OrientationResponse(
                conversation_id=cid,
                reply=_EMERGENCY_REPLY,
                urgency=UrgencyLevel.EMERGENCY,
                recommendation=None,
                provider=self._extraction_llm.provider_name,
            )

        # ── LLM: Extracción de síntomas (entre Layer 1 y 2) ──────────────────
        analysis: SymptomAnalysis = await self._extract_symptoms(intake.clean_message)

        # ── Layer 2: Matcher (con búsqueda en ChromaDB) ───────────────────────
        match = self._reasoning.match(
            intake=intake,
            analysis=analysis,
            search_service=self._search_service,
        )

        # ── Layer 3: Output ───────────────────────────────────────────────────
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
            cleaned = self._extract_json_payload(raw)
            data = json.loads(cleaned)
            urgency = data.get("urgency", "normal")
            valid_urgencies = {level.value for level in UrgencyLevel}
            if urgency not in valid_urgencies:
                urgency = UrgencyLevel.NORMAL.value
            return SymptomAnalysis(
                symptoms=data.get("symptoms", []),
                suggested_specialties=data.get("suggested_specialties", []),
                urgency=UrgencyLevel(urgency),
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

    @staticmethod
    def _extract_json_payload(raw_text: str) -> str:
        """Extract first JSON object from model output, tolerating wrappers."""
        stripped = (
            raw_text.strip()
            .removeprefix("```json")
            .removeprefix("```")
            .removesuffix("```")
            .strip()
        )

        if stripped.startswith("{") and stripped.endswith("}"):
            return stripped

        start = stripped.find("{")
        end = stripped.rfind("}")
        if start != -1 and end != -1 and end > start:
            return stripped[start:end + 1]

        raise ValueError("No JSON object found in model output")

    def _build_context_strings(self, intake: IntakeResult) -> tuple[str, str]:
        """Construye las cadenas de contexto para los prompts del output layer."""
        patient_ctx_str = "No se cargaron datos del paciente."
        insurance_ctx_str = "No se encontró un plan de seguro activo."

        if intake.patient_context:
            loc = intake.patient_context.preferred_location or "No especificada"
            name = intake.identity.display_name or intake.patient_context.display_name or "No especificado"
            cedula = intake.identity.cedula or intake.patient_context.cedula or "No especificada"
            patient_ctx_str = (
                f"Nombre preferido: {name}. "
                f"Cédula: {cedula}. "
                f"Ubicación preferida: {loc}."
            )
        elif intake.identity.display_name or intake.identity.cedula:
            name = intake.identity.display_name or "No especificado"
            cedula = intake.identity.cedula or "No especificada"
            patient_ctx_str = f"Nombre preferido: {name}. Cédula: {cedula}."

        if intake.plan:
            plan = intake.plan
            specialties_str = ", ".join(plan.covered_specialties) or "No especificadas"
            insurance_ctx_str = (
                f"Plan: {plan.plan_name} — {plan.insurer}. "
                f"Especialidades cubiertas: {specialties_str}."
            )

        return patient_ctx_str, insurance_ctx_str
