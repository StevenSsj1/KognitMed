"""Layer 1 agent (input intake): validate and normalize patient message."""

from __future__ import annotations

import re
import structlog
import unicodedata
from typing import ClassVar

from pydantic import BaseModel, Field

from kognitmed.domain.models.orientador import (
    InsurancePlan,
    PatientContext,
    UrgencyLevel,
)

log = structlog.get_logger(__name__)

_EMERGENCY_KEYWORDS: frozenset[str] = frozenset(
    {
        "infarto",
        "paro",
        "paro cardiaco",
        "no puedo respirar",
        "dificultad para respirar",
        "dificultad respirar",
        "perdida de consciencia",
        "perdi el conocimiento",
        "convulsion",
        "sangrado abundante",
        "hemorragia",
        "dolor en el pecho",
        "dolor pecho",
        "dolor toracico",
        "accidente cerebrovascular",
        "derrame cerebral",
        "stroke",
        "quemadura grave",
        "envenenamiento",
        "intoxicacion",
    }
)

_MIN_MSG_LEN: int = 3
_MAX_MSG_LEN: int = 2048
_WORK_RELATED_KEYWORDS: frozenset[str] = frozenset(
    {
        "trabajo",
        "laboral",
        "empleo",
        "asignado",
        "asignacion",
        "puesto",
        "cargo",
        "jornada",
        "turno",
        "empresa",
        "funcion",
        "rol",
        "actividad",
    }
)


class IdentityContext(BaseModel):
    """Identity fields required for work-related conversations."""

    display_name: str | None = None
    cedula: str | None = None


class IntakeResult(BaseModel):
    """Validated and normalized input passed to the reasoning layer."""

    raw_message: str = Field(description="Original patient message.")
    clean_message: str = Field(description="Normalized message for downstream processing.")
    has_plan: bool = Field(description="True if the patient has an active insurance plan.")
    plan: InsurancePlan | None = Field(default=None)
    patient_context: PatientContext | None = Field(default=None)
    fast_emergency_flag: bool = Field(
        default=False,
        description="True if emergency keywords are detected by deterministic heuristics.",
    )
    urgency_hint: UrgencyLevel = Field(default=UrgencyLevel.NORMAL)
    validation_errors: list[str] = Field(default_factory=list)
    is_work_related: bool = Field(default=False)
    identity: IdentityContext = Field(default_factory=IdentityContext)
    missing_identity_fields: list[str] = Field(default_factory=list)


class IntakeAgent:
    """Entry layer for input quality checks and emergency pre-screening."""

    _CEDULA_PATTERN: ClassVar[re.Pattern[str]] = re.compile(r"\b\d{8,13}\b")
    _NAME_PATTERN: ClassVar[re.Pattern[str]] = re.compile(
        r"(?:mi nombre es|me llamo|soy)\s+([A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+(?:\s+[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+){0,3})",
        flags=re.IGNORECASE,
    )

    def process(
        self,
        raw_message: str,
        patient_context: PatientContext | None = None,
        history: list[dict[str, str]] | None = None,
    ) -> IntakeResult:
        """Validate and normalize raw input. Never raises on user data."""
        errors: list[str] = []

        if not isinstance(raw_message, str):
            raw_message = str(raw_message)

        clean = self._normalize(raw_message)

        if len(clean) < _MIN_MSG_LEN:
            errors.append("El mensaje es demasiado corto para ser analizado.")

        if len(clean) > _MAX_MSG_LEN:
            errors.append(f"El mensaje supera el límite de {_MAX_MSG_LEN} caracteres.")
            clean = clean[:_MAX_MSG_LEN]

        plan = patient_context.plan if patient_context else None

        emergency_scan = self._prepare_for_keyword_scan(clean)
        fast_emergency = self._contains_emergency_keyword(emergency_scan)
        urgency_hint = UrgencyLevel.EMERGENCY if fast_emergency else UrgencyLevel.NORMAL

        is_work_related = self._is_work_related_query(emergency_scan)
        identity = self._resolve_identity(
            current_message=clean,
            patient_context=patient_context,
            history=history or [],
        )
        missing_identity_fields = self._missing_identity_fields(identity)

        if errors:
            log.warning("intake_validation_errors", errors=errors)

        log.info(
            "intake_processed",
            msg_len=len(clean),
            has_plan=plan is not None,
            fast_emergency=fast_emergency,
            work_related=is_work_related,
            has_identity=not missing_identity_fields,
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
            is_work_related=is_work_related,
            identity=identity,
            missing_identity_fields=missing_identity_fields,
        )

    @staticmethod
    def _normalize(text: str) -> str:
        """Normalize whitespace and remove control-like noise."""
        text = re.sub(r"[^\S\n]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    @staticmethod
    def _prepare_for_keyword_scan(text: str) -> str:
        """Lowercase + accent-insensitive representation for emergency keywords."""
        lowered = text.casefold()
        normalized = unicodedata.normalize("NFKD", lowered)
        ascii_text = "".join(ch for ch in normalized if not unicodedata.combining(ch))
        cleaned = re.sub(r"[^a-z0-9\\s]", " ", ascii_text)
        cleaned = re.sub(r"\\s+", " ", cleaned).strip()
        return cleaned

    @staticmethod
    def _contains_emergency_keyword(normalized_text: str) -> bool:
        """Match emergency terms by token boundaries to reduce false positives."""
        padded = f" {normalized_text} "
        for keyword in _EMERGENCY_KEYWORDS:
            if f" {keyword} " in padded:
                return True
        return False

    @staticmethod
    def _is_work_related_query(normalized_text: str) -> bool:
        padded = f" {normalized_text} "
        for keyword in _WORK_RELATED_KEYWORDS:
            if f" {keyword} " in padded:
                return True
        return False

    def _resolve_identity(
        self,
        *,
        current_message: str,
        patient_context: PatientContext | None,
        history: list[dict[str, str]],
    ) -> IdentityContext:
        display_name = (patient_context.display_name or "").strip() if patient_context else ""
        cedula = (patient_context.cedula or "").strip() if patient_context else ""

        user_texts: list[str] = [
            m.get("content", "")
            for m in history
            if m.get("role") == "user"
        ]
        user_texts.append(current_message)

        if not cedula:
            for text in user_texts:
                if found := self._extract_cedula(text):
                    cedula = found

        if not display_name:
            for text in user_texts:
                if found := self._extract_name(text):
                    display_name = found

        return IdentityContext(
            display_name=display_name or None,
            cedula=cedula or None,
        )

    @staticmethod
    def _missing_identity_fields(identity: IdentityContext) -> list[str]:
        missing: list[str] = []
        if not identity.cedula:
            missing.append("cedula")
        if not identity.display_name:
            missing.append("nombre")
        return missing

    def _extract_cedula(self, text: str) -> str | None:
        normalized = self._prepare_for_keyword_scan(text)
        match = self._CEDULA_PATTERN.search(normalized)
        return match.group(0) if match else None

    def _extract_name(self, text: str) -> str | None:
        match = self._NAME_PATTERN.search(text)
        if not match:
            return None
        return re.sub(r"\s+", " ", match.group(1)).strip().title()
