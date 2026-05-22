"""MediOrientador — orchestrator service.

Orquesta los 3 layers del agente:
  Layer 1 (agents/intake_agent.py)    → valida y normaliza el input
  Layer 2 (agents/reasoning_agent.py) → cruza síntomas con plan de seguro + ChromaDB
  Layer 3 (agents/response_agent.py)  → sintetiza respuesta conversacional + estructura

Flujo de identificación:
  1. El agente pide cédula al paciente.
  2. Busca en MongoDB → obtiene nombre y seguro.
  3. Construye InsurancePlan desde el seguro.
  4. Procede con el análisis de síntomas.

Flujo de seguimiento:
  - Guarda el último MatchResult por conversación.
  - Si el mensaje no contiene síntomas nuevos → responde conversacionalmente
    usando el contexto previo (hospitales, distancias, copago).
"""

from __future__ import annotations

import json
import re
import structlog
from uuid import UUID

from kognitmed.application.orientador_service.agents.intake_agent import IntakeAgent, IntakeResult
from kognitmed.application.orientador_service.agents.reasoning_agent import MatchResult, ReasoningAgent
from kognitmed.application.orientador_service.agents.response_agent import OutputAgent
from kognitmed.application.orientador_service.schemas import (
    OrientationRequest,
    OrientationResponse,
)
from kognitmed.application.users_service.plan_builder import build_insurance_plan
from kognitmed.application.users_service.service import UsersService
from kognitmed.config import Settings
from kognitmed.domain.models.orientador import PatientContext, SymptomAnalysis, UrgencyLevel
from kognitmed.domain.prompts.orientador_prompts import SYMPTOM_INTENT_PROMPT
from kognitmed.infrastructure.database.red_medica_store import RedMedicaSearchService
from kognitmed.infrastructure.llm_providers.base_provider import AbstractLLMProvider
from kognitmed.infrastructure.memory.in_memory_store import InMemoryConversationStore

log = structlog.get_logger(__name__)

_CEDULA_PATTERN = re.compile(r"\b\d{10}\b")

_WELCOME_REPLY = (
    "¡Hola! Soy MediOrientador, tu asistente de orientación médica. "
    "Para poder ayudarte con información personalizada sobre tu cobertura, "
    "por favor compárteme tu número de cédula."
)

_CEDULA_NOT_FOUND_REPLY = (
    "No encontré un usuario registrado con esa cédula. "
    "Por favor verifica el número e intenta de nuevo."
)

_CEDULA_RETRY_REPLY = (
    "No pude identificar un número de cédula en tu mensaje. "
    "Por favor escríbeme tu número de cédula (10 dígitos) para continuar."
)


class MediOrientadorService:
    """
    Agente conversacional de orientación médica y beneficios.

    Flujo:
        0. [Identificación] Pide cédula → busca en MongoDB → carga plan de seguro.
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
        users_service: UsersService | None = None,
    ) -> None:
        self._extraction_llm = extraction_llm
        self._synthesis_llm = synthesis_llm
        self._memory = memory_store
        self._settings = settings
        self._search_service = search_service
        self._users_service = users_service

        self._intake = IntakeAgent()
        self._reasoning = ReasoningAgent()
        self._output = OutputAgent(llm_provider=synthesis_llm)

        # Estado por conversación
        self._identified_users: dict[UUID, PatientContext] = {}
        self._last_match: dict[UUID, MatchResult] = {}
        self._last_intake: dict[UUID, IntakeResult] = {}

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

        # ── Fase 0: Identificación ───────────────────────────────────────────
        if cid not in self._identified_users:
            return await self._handle_identification(cid, request.message, history)

        # Usuario ya identificado — inyectar su contexto
        patient_ctx = self._identified_users[cid]

        # Actualizar coordenadas si el frontend las envía en este request
        if request.latitud is not None and request.longitud is not None:
            patient_ctx.latitud = request.latitud
            patient_ctx.longitud = request.longitud

        request_with_ctx = OrientationRequest(
            conversation_id=cid,
            message=request.message,
            patient_context=patient_ctx,
            latitud=request.latitud,
            longitud=request.longitud,
        )

        # ── Layer 1: Intake ───────────────────────────────────────────────────
        intake: IntakeResult = self._intake.process(
            raw_message=request_with_ctx.message,
            patient_context=request_with_ctx.patient_context,
            history=history,
        )

        if intake.validation_errors:
            error_reply = f"No pude procesar tu consulta: {intake.validation_errors[0]}"
            await self._memory.add_message(conversation_id=cid, role="assistant", content=error_reply)
            return OrientationResponse(
                conversation_id=cid,
                reply=error_reply,
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

        # ── LLM: Extracción de síntomas ──────────────────────────────────────
        analysis: SymptomAnalysis = await self._extract_symptoms(intake.clean_message)

        # ── Detectar seguimiento vs síntomas nuevos ──────────────────────────
        is_followup = self._is_followup(cid, analysis)

        if is_followup:
            # Seguimiento: usar match previo pero responder conversacionalmente
            match = self._last_match[cid]
            prev_intake = self._last_intake.get(cid, intake)

            # Recalcular distancias si ahora tenemos ubicación
            if request.latitud is not None and match.hospitals:
                match = self._reasoning.match(
                    intake=prev_intake,
                    analysis=analysis,
                    search_service=self._search_service,
                    patient_lat=request.latitud,
                    patient_lon=request.longitud,
                )
                self._last_match[cid] = match

            response = await self._handle_followup(
                cid=cid,
                message=request.message,
                match=match,
                intake=prev_intake,
                history=history,
            )
        else:
            # Síntomas nuevos: pipeline completo
            match = self._reasoning.match(
                intake=intake,
                analysis=analysis,
                search_service=self._search_service,
                patient_lat=request.latitud,
                patient_lon=request.longitud,
            )

            self._last_match[cid] = match
            self._last_intake[cid] = intake

            patient_ctx_str, insurance_ctx_str = self._build_context_strings(intake)

            response = await self._output.build_response(
                conversation_id=cid,
                match=match,
                history=history[:-1],
                patient_context_str=patient_ctx_str,
                insurance_context_str=insurance_ctx_str,
            )

        await self._memory.add_message(
            conversation_id=cid, role="assistant", content=response.reply
        )

        log.info("orientador_done", conversation_id=str(cid))
        return response

    async def get_history(self, conversation_id: UUID) -> list[dict[str, str]]:
        """Devuelve el historial de la conversación."""
        return await self._memory.get_history(conversation_id)

    # ── Identificación ───────────────────────────────────────────────────────

    async def _reply_simple(self, cid: UUID, reply: str) -> OrientationResponse:
        """Persiste y retorna una respuesta simple sin recomendación."""
        await self._memory.add_message(conversation_id=cid, role="assistant", content=reply)
        return OrientationResponse(
            conversation_id=cid,
            reply=reply,
            urgency=UrgencyLevel.NORMAL,
            recommendation=None,
            provider=self._extraction_llm.provider_name,
        )

    async def _handle_identification(
        self,
        cid: UUID,
        message: str,
        history: list[dict[str, str]],
    ) -> OrientationResponse:
        """Maneja la fase de identificación del paciente."""

        # Si es el primer mensaje y no trae cédula, dar bienvenida
        user_messages = [m for m in history if m.get("role") == "user"]
        if len(user_messages) == 1 and not _CEDULA_PATTERN.search(message):
            return await self._reply_simple(cid, _WELCOME_REPLY)

        cedula = self._find_cedula(message, history)
        if not cedula:
            return await self._reply_simple(cid, _CEDULA_RETRY_REPLY)

        user = await self._lookup_user(cid, cedula)
        if isinstance(user, OrientationResponse):
            return user  # error response

        return await self._register_user(cid, cedula, user)

    @staticmethod
    def _find_cedula(message: str, history: list[dict[str, str]]) -> str | None:
        """Extrae cédula del mensaje actual o del historial."""
        match = _CEDULA_PATTERN.search(message)
        if match:
            return match.group(0)
        for m in history:
            if m.get("role") == "user":
                hist_match = _CEDULA_PATTERN.search(m.get("content", ""))
                if hist_match:
                    return hist_match.group(0)
        return None

    async def _lookup_user(self, cid: UUID, cedula: str) -> dict | OrientationResponse:
        """Busca al usuario en MongoDB. Retorna dict si OK, OrientationResponse si error."""
        if not self._users_service:
            log.error("orientador_no_users_service")
            return await self._reply_simple(
                cid, "El servicio de usuarios no está disponible en este momento."
            )
        try:
            user = await self._users_service.get_by_cedula(cedula)
        except Exception as exc:
            log.error("orientador_mongo_error", error=str(exc))
            return await self._reply_simple(
                cid,
                "No pude conectarme a la base de datos para verificar tu información. "
                "Por favor intenta de nuevo en unos momentos.",
            )
        if not user:
            return await self._reply_simple(cid, _CEDULA_NOT_FOUND_REPLY)
        return user

    async def _register_user(self, cid: UUID, cedula: str, user: dict) -> OrientationResponse:
        """Construye plan de seguro, registra al usuario y responde con bienvenida."""
        plan = build_insurance_plan(user["seguro"])

        patient_ctx = PatientContext(
            display_name=user["nombre"],
            cedula=cedula,
            plan=plan,
        )
        self._identified_users[cid] = patient_ctx

        seguro_display = user["seguro"].title()
        specialties_count = len(plan.covered_specialties) if plan else 0

        reply = (
            f"¡Bienvenido/a, {user['nombre']}! "
            f"He verificado tu información: estás asegurado/a con **{seguro_display}** "
            f"(plan: {plan.plan_name}), que cubre {specialties_count} especialidades.\n\n"
            f"Ahora cuéntame, ¿qué síntomas presentas o en qué puedo ayudarte?"
        )

        log.info(
            "orientador_user_identified",
            conversation_id=str(cid),
            cedula=cedula,
            seguro=user["seguro"],
        )

        return await self._reply_simple(cid, reply)

    # ── Seguimiento conversacional ────────────────────────────────────────────

    def _is_followup(self, cid: UUID, analysis: SymptomAnalysis) -> bool:
        """Detecta si el mensaje es una pregunta de seguimiento (no síntomas nuevos)."""
        if cid not in self._last_match:
            return False

        # Si la extracción no encontró síntomas reales, es seguimiento
        if not analysis.symptoms:
            return True

        # Si el único "síntoma" es el fallback del mensaje crudo, es seguimiento
        if len(analysis.symptoms) == 1 and analysis.reasoning and "fallback" in analysis.reasoning.lower():
            return True

        # Si sugiere solo Medicina General sin síntomas claros, posible seguimiento
        if (
            analysis.suggested_specialties == ["Medicina General"]
            and analysis.urgency == UrgencyLevel.NORMAL
            and not analysis.is_emergency
            and len(analysis.symptoms) == 1
            and len(analysis.symptoms[0]) < 20
        ):
            return True

        return False

    async def _handle_followup(
        self,
        *,
        cid: UUID,
        message: str,
        match: MatchResult,
        intake: IntakeResult,
        history: list[dict[str, str]],
    ) -> OrientationResponse:
        """Responde a preguntas de seguimiento usando el contexto previo."""
        patient_ctx_str, insurance_ctx_str = self._build_context_strings(intake)

        # Construir resumen detallado de hospitales con distancias para el LLM
        hospitals_detail = self._build_hospitals_detail(match)

        from kognitmed.domain.prompts.orientador_prompts import MEDIO_ORIENTADOR_SYSTEM_PROMPT

        system_prompt = MEDIO_ORIENTADOR_SYSTEM_PROMPT.render(
            patient_context=patient_ctx_str,
            insurance_context=insurance_ctx_str,
        )

        followup_context = (
            f"Contexto de la consulta previa del paciente:\n"
            f"- Especialidad recomendada: {match.chosen_specialty}\n"
            f"- Cobertura: {'Sí' if match.is_covered else 'No'}\n"
            f"- Copago base: ${match.copay_usd:.2f}\n"
            f"- Urgencia: {match.urgency.value}\n"
            f"- {match.coverage_note}\n\n"
            f"Hospitales disponibles (ordenados por cercanía si hay ubicación):\n"
            f"{hospitals_detail}\n\n"
            f"El paciente pregunta: \"{message}\"\n\n"
            f"Responde de forma directa a lo que pregunta. "
            f"Si pregunta por cercanía, usa las distancias en km. "
            f"Si pide hospitales fuera de su red, menciónalo y aclara que no tendría cobertura. "
            f"Si es un saludo o mensaje casual, responde amablemente y pregunta si necesita algo más. "
            f"Máximo 150 palabras. No repitas la misma recomendación anterior si no la pide."
        )

        messages: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt},
            *history[:-1],
            {"role": "user", "content": followup_context},
        ]

        reply = (await self._synthesis_llm.complete(messages, temperature=0.3)).strip()

        log.info("orientador_followup", conversation_id=str(cid))

        recommendation = ReasoningAgent.to_benefit_recommendation(match)
        recommendation.summary = reply

        return OrientationResponse(
            conversation_id=cid,
            reply=reply,
            urgency=match.urgency,
            recommendation=recommendation,
            provider=self._synthesis_llm.provider_name,
        )

    @staticmethod
    def _build_hospitals_detail(match: MatchResult) -> str:
        """Construye un resumen de hospitales con distancia y copago para el LLM."""
        if not match.hospitals:
            return "No se encontraron hospitales disponibles."

        lines: list[str] = []
        for i, h in enumerate(match.hospitals, 1):
            parts = [f"{i}. {h.name}"]
            if h.ciudad:
                parts.append(f"Ciudad: {h.ciudad}")
            if h.distance_km is not None:
                parts.append(f"Distancia: {h.distance_km} km")
            parts.append(f"Copago: ${h.copay_usd:.2f}")
            parts.append(f"En red: {'Sí' if h.is_in_network else 'No'}")
            if h.especialidades:
                parts.append(f"Especialidades: {', '.join(h.especialidades[:5])}")
            lines.append(" | ".join(parts))
        return "\n".join(lines)

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
