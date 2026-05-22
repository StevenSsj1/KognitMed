"""Layer 2 agent (reasoning + retrieval): specialty, coverage, and ChromaDB match."""

from __future__ import annotations

import math
import structlog
from pydantic import BaseModel, Field

from kognitmed.application.orientador_service.agents.intake_agent import IntakeResult
from kognitmed.domain.models.orientador import (
    BenefitRecommendation,
    HospitalRecommendation,
    InsurancePlan,
    SymptomAnalysis,
    UrgencyLevel,
)
from kognitmed.infrastructure.database.red_medica_store import RedMedicaSearchService

log = structlog.get_logger(__name__)

_DEFAULT_COPAY: float = 0.0
_FALLBACK_SPECIALTY: str = "Medicina General"
_MAX_HOSPITALS_FROM_CHROMA: int = 8
_EARTH_RADIUS_KM: float = 6371.0


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great-circle distance in km between two points."""
    lat1_r, lon1_r = math.radians(lat1), math.radians(lon1)
    lat2_r, lon2_r = math.radians(lat2), math.radians(lon2)
    dlat = lat2_r - lat1_r
    dlon = lon2_r - lon1_r
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlon / 2) ** 2
    return _EARTH_RADIUS_KM * 2 * math.asin(math.sqrt(a))


class MatchResult(BaseModel):
    """Result of symptom-to-coverage-to-network matching."""

    chosen_specialty: str = Field(description="Selected specialty after coverage matching.")
    is_covered: bool = Field(description="True if the chosen specialty is covered by the plan.")
    copay_usd: float | None = Field(
        default=None,
        description="Estimated copay in USD. None if no coverage data applies.",
    )
    hospitals: list[HospitalRecommendation] = Field(
        default_factory=list,
        description="Ranked hospitals from ChromaDB and plan context.",
    )
    urgency: UrgencyLevel
    coverage_note: str = Field(default="")
    no_plan_available: bool = Field(default=False)


class ReasoningAgent:
    """Reasoning layer that combines LLM analysis with insurance and Chroma retrieval."""

    def match(
        self,
        intake: IntakeResult,
        analysis: SymptomAnalysis,
        search_service: RedMedicaSearchService | None = None,
        patient_lat: float | None = None,
        patient_lon: float | None = None,
    ) -> MatchResult:
        urgency = self._resolve_urgency(intake, analysis)
        plan: InsurancePlan | None = intake.plan
        ciudad = intake.patient_context.preferred_location if intake.patient_context else None

        # Coordenadas del paciente: parámetro explícito o desde patient_context
        if patient_lat is None and intake.patient_context:
            patient_lat = intake.patient_context.latitud
            patient_lon = intake.patient_context.longitud

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

        hospitals = self._find_hospitals_from_chroma(
            search_service=search_service,
            specialty=chosen_specialty,
            aseguradora=plan.insurer if plan else None,
            ciudad=ciudad,
            copay_base=copay,
            plan=plan,
            patient_lat=patient_lat,
            patient_lon=patient_lon,
        )

        coverage_note = self._build_coverage_note(
            specialty=chosen_specialty,
            is_covered=is_covered,
            copay=copay,
            plan=plan,
            hospitals_found=len(hospitals),
        )

        log.info(
            "reasoning_result",
            specialty=chosen_specialty,
            is_covered=is_covered,
            copay=copay,
            hospitals_count=len(hospitals),
            source="chroma" if search_service else "none",
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

    @staticmethod
    def to_benefit_recommendation(match: MatchResult) -> BenefitRecommendation:
        """Convert match result into the API response contract model."""
        return BenefitRecommendation(
            recommended_specialty=match.chosen_specialty,
            is_covered=match.is_covered,
            estimated_copay_usd=match.copay_usd,
            hospitals=match.hospitals,
            summary="",
            urgency=match.urgency,
        )

    def _resolve_urgency(self, intake: IntakeResult, analysis: SymptomAnalysis) -> UrgencyLevel:
        if intake.fast_emergency_flag:
            return UrgencyLevel.EMERGENCY
        if analysis.is_emergency:
            return UrgencyLevel.EMERGENCY
        return analysis.urgency

    def _find_best_specialty(
        self,
        suggested: list[str],
        plan: InsurancePlan,
    ) -> tuple[str, bool, float | None]:
        covered_lower: dict[str, str] = {s.casefold(): s for s in plan.covered_specialties}

        for specialty in suggested:
            canonical = covered_lower.get(specialty.casefold())
            if canonical:
                copay = plan.copay_by_specialty.get(canonical, _DEFAULT_COPAY)
                return canonical, True, copay

        if _FALLBACK_SPECIALTY.casefold() in covered_lower:
            fallback_name = covered_lower[_FALLBACK_SPECIALTY.casefold()]
            copay = plan.copay_by_specialty.get(fallback_name, _DEFAULT_COPAY)
            return fallback_name, True, copay

        fallback = suggested[0] if suggested else _FALLBACK_SPECIALTY
        return fallback, False, None

    def _find_hospitals_from_chroma(
        self,
        search_service: RedMedicaSearchService | None,
        specialty: str,
        aseguradora: str | None,
        ciudad: str | None,
        copay_base: float | None,
        plan: InsurancePlan | None,
        patient_lat: float | None = None,
        patient_lon: float | None = None,
    ) -> list[HospitalRecommendation]:
        if search_service is None:
            return []

        try:
            raw_results = search_service.find_by_specialty(
                specialty=specialty,
                aseguradora=aseguradora,
                ciudad=ciudad,
                n_results=_MAX_HOSPITALS_FROM_CHROMA,
            )

            if not raw_results and aseguradora:
                log.info(
                    "reasoning_no_results_with_insurer",
                    specialty=specialty,
                    aseguradora=aseguradora,
                )
                raw_results = search_service.find_by_specialty(
                    specialty=specialty,
                    ciudad=ciudad,
                    n_results=_MAX_HOSPITALS_FROM_CHROMA,
                )

            modifier_by_hospital = self._build_copay_modifiers(plan)
            hospitals = [
                self._to_hospital_recommendation(
                    hospital=h,
                    aseguradora=aseguradora,
                    copay_base=copay_base,
                    modifier_by_hospital=modifier_by_hospital,
                    patient_lat=patient_lat,
                    patient_lon=patient_lon,
                )
                for h in raw_results
            ]
            return self._rank_hospitals(hospitals)
        except Exception as exc:
            log.error("reasoning_chroma_search_failed", error=str(exc))
            return []

    @staticmethod
    def _to_hospital_recommendation(
        hospital: dict,
        aseguradora: str | None,
        copay_base: float | None,
        modifier_by_hospital: dict[str, float],
        patient_lat: float | None = None,
        patient_lon: float | None = None,
    ) -> HospitalRecommendation:
        hosp_name = hospital.get("nombre", "")
        modifier = modifier_by_hospital.get(hosp_name.casefold(), 0.0)
        computed_copay = _DEFAULT_COPAY if copay_base is None else max(copay_base + modifier, 0.0)

        in_network = False
        if aseguradora:
            in_network = aseguradora.casefold() in [
                a.casefold() for a in hospital.get("aseguradoras", [])
            ]

        # Calcular distancia si tenemos coordenadas de ambos
        hosp_lat = hospital.get("latitud")
        hosp_lon = hospital.get("longitud")
        distance_km: float | None = None
        if patient_lat is not None and patient_lon is not None and hosp_lat is not None and hosp_lon is not None:
            distance_km = round(_haversine(patient_lat, patient_lon, hosp_lat, hosp_lon), 1)

        return HospitalRecommendation(
            name=hosp_name,
            copay_usd=computed_copay,
            is_in_network=in_network,
            notes=hospital.get("nota") or None,
            ciudad=hospital.get("ciudad"),
            aseguradoras=hospital.get("aseguradoras", []),
            especialidades=hospital.get("especialidades", []),
            latitud=hospital.get("latitud"),
            longitud=hospital.get("longitud"),
            relevance_score=hospital.get("relevance_score"),
            distance_km=distance_km,
        )

    @staticmethod
    def _build_copay_modifiers(plan: InsurancePlan | None) -> dict[str, float]:
        if plan is None:
            return {}

        modifiers: dict[str, float] = {}
        for hospital in plan.network_hospitals:
            name = hospital.get("name")
            if not isinstance(name, str) or not name.strip():
                continue
            modifier = hospital.get("copay_modifier", 0.0)
            try:
                modifiers[name.casefold()] = float(modifier)
            except (TypeError, ValueError):
                continue
        return modifiers

    @staticmethod
    def _rank_hospitals(hospitals: list[HospitalRecommendation]) -> list[HospitalRecommendation]:
        has_distances = any(h.distance_km is not None for h in hospitals)
        return sorted(
            hospitals,
            key=lambda h: (
                not h.is_in_network,
                # Si hay distancias, priorizar cercanía; si no, ignorar
                h.distance_km if has_distances and h.distance_km is not None else 0.0,
                h.copay_usd,
                -(h.relevance_score or 0.0),
                h.name,
            ),
        )

    @staticmethod
    def _build_coverage_note(
        specialty: str,
        is_covered: bool,
        copay: float | None,
        plan: InsurancePlan | None,
        hospitals_found: int,
    ) -> str:
        if plan is None:
            return (
                "No se encontró un plan de seguro activo. "
                "Mostrando hospitales disponibles en la red sin calcular copago."
            )

        if not is_covered:
            return (
                f"La especialidad '{specialty}' no está cubierta en el plan '{plan.plan_name}'. "
                "Te recomendamos verificar alternativas directamente con tu aseguradora."
            )

        copay_str = f"${copay:.2f}" if copay is not None else "no especificado"
        hospitals_str = f" Se encontraron {hospitals_found} centros en red." if hospitals_found else ""
        return (
            f"'{specialty}' está cubierta por el plan '{plan.plan_name}' ({plan.insurer}). "
            f"Copago estimado: {copay_str}.{hospitals_str}"
        )
