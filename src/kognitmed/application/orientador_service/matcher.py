"""Layer 2 — Matcher: cruza síntomas analizados con el plan de seguro.

Recibe el IntakeResult del Layer 1 y el SymptomAnalysis del LLM,
y produce un MatchResult con la especialidad elegida, cobertura,
copago calculado y hospitales ordenados por conveniencia económica.
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


class MatchResult(BaseModel):
    """Resultado del cruce síntoma ↔ plan de seguro."""

    chosen_specialty: str = Field(description="Especialidad seleccionada tras el match.")
    is_covered: bool = Field(description="True si la especialidad está en el plan.")
    copay_usd: float | None = Field(
        default=None,
        description="Copago estimado en USD. None si no está cubierta o sin datos.",
    )
    hospitals: list[HospitalRecommendation] = Field(
        default_factory=list,
        description="Hospitales en red ordenados por copago total ascendente.",
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
    Layer 2: cruce síntoma ↔ especialidad ↔ cobertura.

    Algoritmo:
    1. Si no hay plan disponible → retorna match sin cobertura.
    2. Itera las especialidades sugeridas (ordenadas por relevancia LLM).
    3. Primera que esté en covered_specialties del plan → es la elegida.
    4. Calcula copago = copay_by_specialty[specialty].
    5. Construye lista de hospitales en red con copago total (base + modifier).
    6. Ordena hospitales por copago total ascendente.
    """

    def match(
        self,
        intake: IntakeResult,
        analysis: SymptomAnalysis,
    ) -> MatchResult:
        """Ejecuta el match y retorna un MatchResult completo."""

        urgency = self._resolve_urgency(intake, analysis)

        # ── Sin plan de seguro ────────────────────────────────────────────────
        if not intake.has_plan or intake.plan is None:
            log.info("matcher_no_plan", specialties=analysis.suggested_specialties)
            chosen = (
                analysis.suggested_specialties[0]
                if analysis.suggested_specialties
                else _FALLBACK_SPECIALTY
            )
            return MatchResult(
                chosen_specialty=chosen,
                is_covered=False,
                copay_usd=None,
                hospitals=[],
                urgency=urgency,
                coverage_note="No se encontró un plan de seguro activo. No se puede calcular copago.",
                no_plan_available=True,
            )

        plan: InsurancePlan = intake.plan

        # ── Buscar especialidad cubierta ──────────────────────────────────────
        chosen_specialty, is_covered, copay = self._find_best_specialty(
            analysis.suggested_specialties, plan
        )

        # ── Construir recomendaciones de hospital ─────────────────────────────
        hospitals = self._rank_hospitals(plan, copay)

        coverage_note = self._build_coverage_note(
            specialty=chosen_specialty,
            is_covered=is_covered,
            copay=copay,
            plan=plan,
        )

        log.info(
            "matcher_result",
            specialty=chosen_specialty,
            is_covered=is_covered,
            copay=copay,
            hospitals_count=len(hospitals),
        )

        return MatchResult(
            chosen_specialty=chosen_specialty,
            is_covered=is_covered,
            copay_usd=copay,
            hospitals=hospitals,
            urgency=urgency,
            coverage_note=coverage_note,
            no_plan_available=False,
        )

    # ── Helpers privados ──────────────────────────────────────────────────────

    def _resolve_urgency(self, intake: IntakeResult, analysis: SymptomAnalysis) -> UrgencyLevel:
        """La heurística rápida del intake tiene precedencia sobre el LLM si detectó emergencia."""
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
        Prioriza la primera especialidad sugerida que esté cubierta.
        """
        # Normalización: comparación case-insensitive
        covered_lower: dict[str, str] = {
            s.lower(): s for s in plan.covered_specialties
        }

        for specialty in suggested:
            matched_key = specialty.lower()
            if matched_key in covered_lower:
                canonical = covered_lower[matched_key]
                copay = plan.copay_by_specialty.get(canonical, _DEFAULT_COPAY)
                return canonical, True, copay

        # Ninguna sugerida está cubierta — usar la primera sugerida o fallback
        fallback = suggested[0] if suggested else _FALLBACK_SPECIALTY

        # Último intento: Medicina General como comodín
        if _FALLBACK_SPECIALTY.lower() in covered_lower:
            copay = plan.copay_by_specialty.get(_FALLBACK_SPECIALTY, _DEFAULT_COPAY)
            return _FALLBACK_SPECIALTY, True, copay

        return fallback, False, None

    def _rank_hospitals(
        self,
        plan: InsurancePlan,
        copay_base: float | None,
    ) -> list[HospitalRecommendation]:
        """Construye y ordena hospitales por copago total ascendente."""
        hospitals: list[HospitalRecommendation] = []

        for h in plan.network_hospitals:
            modifier = float(h.get("copay_modifier", 0.0))
            total = (copay_base or 0.0) + modifier

            hospitals.append(
                HospitalRecommendation(
                    name=str(h.get("name", "Hospital")),
                    copay_usd=round(total, 2),
                    is_in_network=True,
                    notes=str(h.get("notes", "")) or None,
                )
            )

        # Ordenar: menor copago primero
        hospitals.sort(key=lambda h: h.copay_usd)
        return hospitals

    @staticmethod
    def _build_coverage_note(
        specialty: str,
        is_covered: bool,
        copay: float | None,
        plan: InsurancePlan,
    ) -> str:
        if not is_covered:
            return (
                f"La especialidad '{specialty}' no está cubierta en el plan {plan.plan_name}. "
                "Considera contactar a tu aseguradora para verificar opciones."
            )
        copay_str = f"${copay:.2f}" if copay is not None else "no especificado"
        return (
            f"'{specialty}' está cubierta en el plan {plan.plan_name} "
            f"({plan.insurer}). Copago estimado: {copay_str}."
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
