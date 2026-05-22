"""Build an InsurancePlan from the insurer name and the enriched dataset."""

from __future__ import annotations

import json
from pathlib import Path

from kognitmed.domain.models.orientador import InsurancePlan

_DATASET_PATH = Path(__file__).parent.parent.parent.parent.parent / "doc" / "dataset_red_medica_enriched.json"

# Copagos base por aseguradora (USD) — valores representativos Ecuador
_COPAY_TABLES: dict[str, dict[str, float]] = {
    "saludsa": {
        "Medicina General": 8.0,
        "Pediatría": 10.0,
        "Ginecología": 15.0,
        "Cardiología": 25.0,
        "Neurología": 25.0,
        "Traumatología": 20.0,
        "Cirugía General": 30.0,
        "Oncología": 35.0,
        "UCI": 50.0,
        "Gastroenterología": 20.0,
        "Oftalmología": 15.0,
        "Medicina Interna": 12.0,
        "_default": 15.0,
    },
    "humana": {
        "Medicina General": 5.0,
        "Pediatría": 8.0,
        "Ginecología": 12.0,
        "Cardiología": 20.0,
        "Neurología": 22.0,
        "Traumatología": 18.0,
        "Cirugía General": 28.0,
        "Oncología": 30.0,
        "UCI": 45.0,
        "Gastroenterología": 18.0,
        "Urología": 20.0,
        "Medicina Interna": 10.0,
        "_default": 12.0,
    },
    "bupa": {
        "Medicina General": 10.0,
        "Pediatría": 12.0,
        "Ginecología": 18.0,
        "Cardiología": 28.0,
        "Neurología": 28.0,
        "Traumatología": 22.0,
        "Cirugía General": 32.0,
        "Oncología": 40.0,
        "UCI": 55.0,
        "Gastroenterología": 22.0,
        "Urología": 22.0,
        "Medicina Interna": 14.0,
        "_default": 18.0,
    },
    "bmi": {
        "Medicina General": 6.0,
        "Pediatría": 8.0,
        "Ginecología": 14.0,
        "Cardiología": 22.0,
        "Neurología": 22.0,
        "Traumatología": 18.0,
        "Cirugía General": 26.0,
        "Oncología": 32.0,
        "UCI": 48.0,
        "Gastroenterología": 18.0,
        "Urología": 18.0,
        "Medicina Interna": 10.0,
        "_default": 14.0,
    },
    "ecuasanitas": {
        "Medicina General": 4.0,
        "Pediatría": 6.0,
        "Ginecología": 10.0,
        "Cardiología": 18.0,
        "Neurología": 18.0,
        "Traumatología": 15.0,
        "Cirugía General": 22.0,
        "Oncología": 28.0,
        "UCI": 40.0,
        "Gastroenterología": 15.0,
        "Medicina Interna": 8.0,
        "_default": 10.0,
    },
}

_PLAN_NAMES: dict[str, str] = {
    "saludsa": "Plan Star Saludsa",
    "humana": "Plan Integral Humana",
    "bupa": "Plan Global Bupa",
    "bmi": "Plan Red BMI",
    "ecuasanitas": "Plan Familiar Ecuasanitas",
}

_dataset_cache: dict | None = None


def _load_dataset() -> dict:
    global _dataset_cache
    if _dataset_cache is not None:
        return _dataset_cache
    if _DATASET_PATH.exists():
        _dataset_cache = json.loads(_DATASET_PATH.read_text(encoding="utf-8"))
    else:
        _dataset_cache = {}
    return _dataset_cache


def build_insurance_plan(seguro: str) -> InsurancePlan | None:
    """Build a full InsurancePlan for the given insurer name."""
    seguro_lower = seguro.strip().lower()

    if seguro_lower not in _COPAY_TABLES:
        return None

    dataset = _load_dataset()
    copay_table = _COPAY_TABLES[seguro_lower]
    default_copay = copay_table.get("_default", 15.0)

    # Extraer hospitales y especialidades de la red del asegurador
    insurer_hospitals = dataset.get("por_aseguradora", {}).get(seguro_lower, [])

    # Recolectar todas las especialidades cubiertas
    all_specialties: set[str] = set()
    network_hospitals: list[dict[str, object]] = []

    for h in insurer_hospitals:
        specs = h.get("especialidades", [])
        all_specialties.update(specs)
        network_hospitals.append({
            "name": h.get("nombre", ""),
            "copay_modifier": 0.0,
        })

    # Construir copay_by_specialty con todas las especialidades encontradas
    copay_by_specialty: dict[str, float] = {}
    for spec in all_specialties:
        copay_by_specialty[spec] = copay_table.get(spec, default_copay)

    return InsurancePlan(
        plan_name=_PLAN_NAMES.get(seguro_lower, f"Plan {seguro.title()}"),
        insurer=seguro_lower,
        copay_by_specialty=copay_by_specialty,
        network_hospitals=network_hospitals,
        covered_specialties=sorted(all_specialties),
        emergency_covered=True,
    )
