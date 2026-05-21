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
        help="Prueba de búsqueda semántica tras la ingesta",
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

    # ── Modo búsqueda de prueba ────────────────────────────────────────────────
    if args.search:
        print(f"\n🔍 Búsqueda de prueba: '{args.search}'")
        results = search_svc.search(args.search, n_results=3)
        for i, h in enumerate(results, 1):
            esp = ", ".join(h["especialidades"][:4]) or "sin especialidades"
            aseg = ", ".join(h["aseguradoras"])
            print(f"\n  {i}. {h['nombre']} ({h['ciudad']})")
            print(f"     Especialidades: {esp}")
            print(f"     Aseguradoras  : {aseg}")
            print(f"     Relevancia    : {h['relevance_score']:.3f}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
