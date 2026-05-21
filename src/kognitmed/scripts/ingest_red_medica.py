"""Script de ingesta de la red médica en ChromaDB.

Uso:
    uv run python -m kognitmed.scripts.ingest_red_medica
    uv run python -m kognitmed.scripts.ingest_red_medica --path doc/dataset_red_medica_enriched.json
    uv run python -m kognitmed.scripts.ingest_red_medica --info   (solo muestra estado)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import structlog

# Configurar logging básico antes de importar el resto
import logging
logging.basicConfig(level=logging.INFO, format="%(message)s")
log = structlog.get_logger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingesta de red médica en ChromaDB (modo archivo)")
    parser.add_argument(
        "--path",
        default="doc/dataset_red_medica_enriched.json",
        help="Ruta al JSON de la red médica (default: doc/dataset_red_medica_enriched.json)",
    )
    parser.add_argument(
        "--info",
        action="store_true",
        help="Solo muestra el estado de la colección sin ingestar",
    )
    parser.add_argument(
        "--search",
        default="",
        help="Prueba de búsqueda semántica libre tras la ingesta",
    )
    parser.add_argument(
        "--specialty",
        default="",
        help="Filtro exacto por especialidad (ej: Pediatría). Garantiza que todos los resultados la tienen.",
    )
    parser.add_argument(
        "--ciudad",
        default="",
        help="Filtro por ciudad (ej: Quito)",
    )
    parser.add_argument(
        "--aseguradora",
        default="",
        help="Filtro por aseguradora (ej: humana, bupa, bmi, saludsa)",
    )
    parser.add_argument(
        "--n",
        type=int,
        default=10,
        help="Número máximo de resultados a mostrar (default: 10)",
    )
    args = parser.parse_args()

    # Importar config y Chroma
    from kognitmed.config import get_settings
    from kognitmed.infrastructure.database.chroma import get_chroma_client
    from kognitmed.infrastructure.database.red_medica_store import (
        RedMedicaIngestService,
        RedMedicaSearchService,
    )

    settings = get_settings()
    print(f"📁 ChromaDB persist path: {settings.chroma_persist_path}")

    client = get_chroma_client(settings)
    ingest_svc = RedMedicaIngestService(client)
    search_svc = RedMedicaSearchService(client)

    # ── Modo info ──────────────────────────────────────────────────────────────
    info = ingest_svc.get_collection_info()
    print(f"\n📊 Colección '{info['collection']}': {info['total_documents']} documentos [{info['status']}]")

    if args.info:
        return 0

    # ── Modo ingesta ───────────────────────────────────────────────────────────
    dataset_path = Path(args.path)
    if not dataset_path.exists():
        print(f"\n❌ Archivo no encontrado: {dataset_path}", file=sys.stderr)
        return 1

    print(f"\n🔄 Ingresando: {dataset_path} ...")
    result = ingest_svc.ingest_from_file(dataset_path)
    print(f"✅ Ingesta completada:")
    print(f"   ├─ Insertados : {result['inserted']}")
    print(f"   ├─ Saltados   : {result['skipped']} (ya existían)")
    print(f"   └─ Total      : {result['total']}")

    # ── Modo búsqueda de prueba ───────────────────────────────────────────────────────
    if args.search or args.specialty:
        ciudad = args.ciudad or None
        aseguradora = args.aseguradora or None

        if args.specialty:
            label = f"Especialidad exacta: '{args.specialty}'"
            if ciudad: label += f" | Ciudad: {ciudad}"
            if aseguradora: label += f" | Aseguradora: {aseguradora}"
            print(f"\n🔍 {label}")
            results = search_svc.find_by_specialty(
                specialty=args.specialty,
                aseguradora=aseguradora,
                ciudad=ciudad,
                n_results=args.n,
            )
        else:
            label = f"Búsqueda: '{args.search}'"
            if ciudad: label += f" | Ciudad: {ciudad}"
            if aseguradora: label += f" | Aseguradora: {aseguradora}"
            print(f"\n🔍 {label}")
            results = search_svc.search(
                query=args.search,
                n_results=args.n,
                ciudad=ciudad,
                aseguradora=aseguradora,
            )

        print(f"   Encontrados: {len(results)} hospitales\n")
        for i, h in enumerate(results, 1):
            esp_all = ", ".join(h["especialidades"]) or "sin especialidades"
            aseg = ", ".join(h["aseguradoras"]) or "sin aseguradora"
            ciudad_str = h['ciudad'] or 'ciudad no especificada'
            print(f"  {i:2d}. {h['nombre']} ({ciudad_str})")
            print(f"      Especialidades : {esp_all}")
            print(f"      Aseguradoras   : {aseg}")
            print(f"      Relevancia     : {h['relevance_score']:.3f}")
            if h.get('nota'):
                print(f"      Nota           : {h['nota']}")
            print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
