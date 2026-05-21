"""Layer 2 — Matcher: cruza síntomas analizados con el plan de seguro y la red médica real.

Recibe el IntakeResult del Layer 1 y el SymptomAnalysis del LLM,
consulta ChromaDB para encontrar hospitales reales que tienen la especialidad,
calcula copagos desde el plan de seguro y produce un MatchResult.
Este layer es puro Python — NO llama al LLM.
"""

from __future__ import annotations

import structlog
from pydantic import BaseModel, Field

from kognitmed.application.orientador_service.intake import IntakeResult
from kognitmed.domain.models.orientador import (
    BenefitRecommendation,
    HospitalRecommendation,
    InsurancePlan,
    SymptomAnalysis,
    UrgencyLevel,
)

log = structlog.get_logger(__name__)

# Copago por defecto si la especialidad está cubierta pero sin valor explícito
_DEFAULT_COPAY: float = 0.0

# Especialidad de último recurso si ninguna sugerida está cubierta
_FALLBACK_SPECIALTY: str = "Medicina General"

# Cuántos hospitales buscar en Chroma por especialidad
_MAX_HOSPITALS_FROM_CHROMA: int = 8


class MatchResult(BaseModel):
    """Resultado del cruce síntoma ↔ plan de seguro ↔ red médica real."""

    chosen_specialty: str = Field(description="Especialidad seleccionada tras el match.")
    is_covered: bool = Field(description="True si la especialidad está en el plan.")
    copay_usd: float | None = Field(
        default=None,
        description="Copago estimado en USD. None si no está cubierta o sin datos.",
    )
    hospitals: list[HospitalRecommendation] = Field(
        default_factory=list,
        description="Hospitales en red obtenidos de ChromaDB, ordenados por relevancia y copago.",
    )
    urgency: UrgencyLevel
    coverage_note: str = Field(
        default="",
        description="Nota explicativa sobre la cobertura encontrada.",
    )
    no_plan_available: bool = Field(
        default=False,
        description="True si el paciente no proporcionó plan de seguro.",
    )


class MatcherLayer:
    """
    Layer 2: cruce síntoma ↔ especialidad ↔ cobertura ↔ red médica real.

    Algoritmo:
    1. Si no hay plan → busca hospitales en Chroma sin filtro de aseguradora.
    2. Itera las especialidades sugeridas (ordenadas por relevancia LLM).
    3. Primera que esté en covered_specialties del plan → es la elegida.
    4. Consulta ChromaDB: hospitales con esa especialidad [+ aseguradora + ciudad].
    5. Calcula copago = copay_by_specialty[specialty] del plan.
    6. Construye HospitalRecommendation con datos reales de Chroma.
    """

    def match(
        self,
        intake: IntakeResult,
        analysis: SymptomAnalysis,
        # Inyección opcional del servicio de búsqueda (None = sin Chroma)
        search_service=None,
    ) -> MatchResult:
        """Ejecuta el match y retorna un MatchResult completo."""

        urgency = self._resolve_urgency(intake, analysis)
        plan: InsurancePlan | None = intake.plan
        ciudad = intake.patient_context.preferred_location if intake.patient_context else None

        # ── Elegir especialidad ────────────────────────────────────────────────
        if plan:
            chosen_specialty, is_covered, copay = self._find_best_specialty(
                analysis.suggested_specialties, plan
            )
        else:
            chosen_specialty = (
                analysis.suggested_specialties[0]
                if analysis.suggested_specialties
                else _FALLBACK_SPECIALTY
            )
            is_covered = False
            copay = None

        # ── Buscar hospitales en Chroma (fuente de verdad) ─────────────────────
        hospitals = self._find_hospitals_from_chroma(
            search_service=search_service,
            specialty=chosen_specialty,
            aseguradora=plan.insurer if plan else None,
            ciudad=ciudad,
            copay_base=copay,
        )

        # ── Nota de cobertura ──────────────────────────────────────────────────
        if plan:
            coverage_note = self._build_coverage_note(
                specialty=chosen_specialty,
                is_covered=is_covered,
                copay=copay,
                plan=plan,
                hospitals_found=len(hospitals),
            )
        else:
            coverage_note = (
                "No se encontró un plan de seguro activo. "
                "Mostrando hospitales disponibles en la red sin calcular copago."
            )

        log.info(
            "matcher_result",
            specialty=chosen_specialty,
            is_covered=is_covered,
            copay=copay,
            hospitals_count=len(hospitals),
            source="chroma" if search_service else "static",
        )

        return MatchResult(
            chosen_specialty=chosen_specialty,
            is_covered=is_covered,
            copay_usd=copay,
            hospitals=hospitals,
            urgency=urgency,
            coverage_note=coverage_note,
            no_plan_available=plan is None,
        )

    # ── Helpers privados ──────────────────────────────────────────────────────

    def _resolve_urgency(self, intake: IntakeResult, analysis: SymptomAnalysis) -> UrgencyLevel:
        """La heurística rápida del intake tiene precedencia sobre el LLM."""
        if intake.fast_emergency_flag:
            return UrgencyLevel.EMERGENCY
        return analysis.urgency

    def _find_best_specialty(
        self,
        suggested: list[str],
        plan: InsurancePlan,
    ) -> tuple[str, bool, float | None]:
        """
        Retorna (specialty, is_covered, copay).
        Prioriza la primera especialidad sugerida que esté cubierta por el plan.
        """
        covered_lower: dict[str, str] = {
            s.lower(): s for s in plan.covered_specialties
        }

        for specialty in suggested:
            if specialty.lower() in covered_lower:
                canonical = covered_lower[specialty.lower()]
                copay = plan.copay_by_specialty.get(canonical, _DEFAULT_COPAY)
                return canonical, True, copay

        # Fallback: Medicina General como comodín
        if _FALLBACK_SPECIALTY.lower() in covered_lower:
            copay = plan.copay_by_specialty.get(_FALLBACK_SPECIALTY, _DEFAULT_COPAY)
            return _FALLBACK_SPECIALTY, True, copay

        fallback = suggested[0] if suggested else _FALLBACK_SPECIALTY
        return fallback, False, None

    def _find_hospitals_from_chroma(
        self,
        search_service,
        specialty: str,
        aseguradora: str | None,
        ciudad: str | None,
        copay_base: float | None,
    ) -> list[HospitalRecommendation]:
        """
        Busca hospitales reales en ChromaDB.
        Si no hay search_service disponible, retorna lista vacía.
        """
        if search_service is None:
            return []

        try:
            raw_results = search_service.find_by_specialty(
                specialty=specialty,
                aseguradora=aseguradora,
                ciudad=ciudad,
                n_results=_MAX_HOSPITALS_FROM_CHROMA,
            )

            # Si no hay resultados con filtro de aseguradora, intentar sin ese filtro
            if not raw_results and aseguradora:
                log.info(
                    "matcher_chroma_no_results_with_insurer",
                    specialty=specialty,
                    aseguradora=aseguradora,
                )
                raw_results = search_service.find_by_specialty(
                    specialty=specialty,
                    ciudad=ciudad,
                    n_results=_MAX_HOSPITALS_FROM_CHROMA,
                )

            return [
                HospitalRecommendation(
                    name=h["nombre"],
                    copay_usd=copay_base or _DEFAULT_COPAY,
                    is_in_network=bool(aseguradora and aseguradora.lower() in [
                        a.lower() for a in h.get("aseguradoras", [])
                    ]),
                    notes=h.get("nota") or None,
                    ciudad=h.get("ciudad"),
                    aseguradoras=h.get("aseguradoras", []),
                    especialidades=h.get("especialidades", []),
                    latitud=h.get("latitud"),
                    longitud=h.get("longitud"),
                    relevance_score=h.get("relevance_score"),
                )
                for h in raw_results
            ]

        except Exception as exc:
            log.error("matcher_chroma_search_failed", error=str(exc))
            return []

    @staticmethod
    def _build_coverage_note(
        specialty: str,
        is_covered: bool,
        copay: float | None,
        plan: InsurancePlan,
        hospitals_found: int,
    ) -> str:
        if not is_covered:
            return (
                f"La especialidad '{specialty}' no está cubierta en el plan '{plan.plan_name}'. "
                "Considera contactar a tu aseguradora para verificar opciones."
            )
        copay_str = f"${copay:.2f}" if copay is not None else "no especificado"
        hospitals_str = f" Se encontraron {hospitals_found} centros en la red." if hospitals_found else ""
        return (
            f"'{specialty}' está cubierta en tu plan '{plan.plan_name}' "
            f"({plan.insurer}). Copago estimado: {copay_str}.{hospitals_str}"
        )

    def to_benefit_recommendation(self, match: MatchResult) -> BenefitRecommendation:
        """Convierte un MatchResult al modelo de dominio BenefitRecommendation."""
        return BenefitRecommendation(
            recommended_specialty=match.chosen_specialty,
            is_covered=match.is_covered,
            estimated_copay_usd=match.copay_usd,
            hospitals=match.hospitals,
            summary=match.coverage_note,
            urgency=match.urgency,
        )
