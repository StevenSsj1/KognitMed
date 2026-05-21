"""Red Médica vector store — ingesta y recuperación desde ChromaDB (modo archivo).

Transforma cada hospital del dataset en un documento semántico:
  - Texto buscable: nombre + ciudad + especialidades + aseguradoras + nota
  - Metadata estructurada: para filtros exactos (ciudad, aseguradora, especialidad)
  - ID determinista: evita duplicados si se vuelve a ejecutar la ingesta

Colección única: "red_medica"
"""

from __future__ import annotations

import hashlib
import json
import structlog
from pathlib import Path
from typing import Any

import chromadb
from chromadb import ClientAPI

log = structlog.get_logger(__name__)

_COLLECTION_NAME = "red_medica"

# ── Helpers de transformación ─────────────────────────────────────────────────


def _hospital_to_document(hospital: dict[str, Any]) -> tuple[str, str, dict[str, str]]:
    """
    Convierte un registro de hospital a (doc_id, texto_buscable, metadata).

    El texto buscable está optimizado para búsqueda semántica:
    describe el hospital con lenguaje natural para que los embeddings
    capturen similitud con queries de síntomas y especialidades.
    """
    nombre = hospital.get("nombre", "").strip()
    ciudad = hospital.get("ciudad", "").strip() or "Ecuador"
    especialidades: list[str] = hospital.get("especialidades", []) or []
    aseguradoras: list[str] = hospital.get("aseguradoras", []) or []
    nota = hospital.get("nota", "").strip()
    grupo = hospital.get("grupo", "").strip()

    # Texto semántico para embeddings
    esp_str = ", ".join(especialidades) if especialidades else "servicio general"
    aseg_str = ", ".join(aseguradoras) if aseguradoras else "sin aseguradora"

    text_parts = [
        f"Hospital: {nombre}.",
        f"Ciudad: {ciudad}.",
        f"Especialidades disponibles: {esp_str}.",
        f"Aseguradoras que cubren este centro: {aseg_str}.",
    ]
    if nota:
        text_parts.append(f"Nota de cobertura: {nota}.")
    if grupo:
        text_parts.append(f"Grupo hospitalario: {grupo}.")

    text = " ".join(text_parts)

    # ID determinista basado en nombre normalizado
    doc_id = "hosp_" + hashlib.md5(nombre.lower().encode()).hexdigest()[:12]

    # Metadata para filtros exactos (Chroma solo acepta str/int/float/bool)
    metadata: dict[str, str] = {
        "nombre": nombre,
        "ciudad": ciudad,
        "aseguradoras": json.dumps(aseguradoras, ensure_ascii=False),
        "especialidades": json.dumps(especialidades, ensure_ascii=False),
        "latitud": str(hospital.get("latitud") or ""),
        "longitud": str(hospital.get("longitud") or ""),
        "nota": nota,
        "grupo": grupo,
        "tiene_coordenadas": "true" if hospital.get("latitud") is not None else "false",
        "tiene_especialidades": "true" if especialidades else "false",
    }

    return doc_id, text, metadata


# ── Servicio de ingesta ───────────────────────────────────────────────────────


class RedMedicaIngestService:
    """
    Carga el dataset de red médica en ChromaDB (colección 'red_medica').

    Usa IDs deterministas para ser idempotente — ejecutar varias veces
    no genera duplicados.
    """

    def __init__(self, chroma_client: ClientAPI) -> None:
        self._client = chroma_client

    def ingest_from_file(self, dataset_path: str | Path) -> dict[str, int]:
        """
        Lee el JSON de red médica e ingesta todos los hospitales en Chroma.

        Returns:
            Diccionario con conteos: inserted, skipped, total.
        """
        path = Path(dataset_path)
        if not path.exists():
            raise FileNotFoundError(f"Dataset no encontrado: {path}")

        log.info("red_medica_ingest_start", path=str(path))

        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        hospitales: list[dict[str, Any]] = data.get("hospitales_unicos", [])
        if not hospitales:
            log.warning("red_medica_ingest_empty_dataset")
            return {"inserted": 0, "skipped": 0, "total": 0}

        collection = self._client.get_or_create_collection(
            name=_COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )

        # Chequear cuántos ya existen (para idempotencia)
        existing = collection.get(include=[])
        existing_ids: set[str] = set(existing.get("ids", []))

        ids, texts, metadatas = [], [], []

        for hospital in hospitales:
            doc_id, text, metadata = _hospital_to_document(hospital)
            if doc_id in existing_ids:
                continue  # ya indexado, skip
            ids.append(doc_id)
            texts.append(text)
            metadatas.append(metadata)

        inserted = 0
        if ids:
            # Chromadb PersistentClient genera embeddings internamente con el modelo por defecto
            # (all-MiniLM-L6-v2 de sentence-transformers) — no necesita OpenAI para esto
            collection.add(documents=texts, ids=ids, metadatas=metadatas)
            inserted = len(ids)
            log.info("red_medica_ingest_done", inserted=inserted, skipped=len(hospitales) - inserted)
        else:
            log.info("red_medica_ingest_all_skipped", total=len(hospitales))

        return {
            "inserted": inserted,
            "skipped": len(hospitales) - inserted,
            "total": len(hospitales),
        }

    def get_collection_info(self) -> dict[str, Any]:
        """Devuelve información básica de la colección en Chroma."""
        try:
            collection = self._client.get_collection(_COLLECTION_NAME)
            count = collection.count()
            return {
                "collection": _COLLECTION_NAME,
                "total_documents": count,
                "status": "ready",
            }
        except Exception:
            return {
                "collection": _COLLECTION_NAME,
                "total_documents": 0,
                "status": "not_found",
            }


# ── Servicio de búsqueda ──────────────────────────────────────────────────────


class RedMedicaSearchService:
    """
    Búsqueda semántica sobre la red médica indexada en Chroma.

    Permite consultas como:
      - "hospital de cardiología en Quito" → hospitales relevantes
      - "clínica cubierta por humana con pediatría" → filtros + semántica
    """

    def __init__(self, chroma_client: ClientAPI) -> None:
        self._client = chroma_client
        self._collection = None

    def _get_collection(self):
        if self._collection is None:
            self._collection = self._client.get_or_create_collection(
                name=_COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"},
            )
        return self._collection

    def search(
        self,
        query: str,
        n_results: int = 5,
        ciudad: str | None = None,
        aseguradora: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Búsqueda semántica con filtros opcionales.

        Args:
            query: Texto de búsqueda (ej: "cardiología urgente").
            n_results: Número máximo de resultados.
            ciudad: Filtro exacto por ciudad (ej: "Quito").
            aseguradora: Filtro por aseguradora en metadata JSON.

        Returns:
            Lista de hospitales con sus metadatos y score de relevancia.
        """
        collection = self._get_collection()

        # Construir where clause para filtros exactos
        where: dict[str, Any] | None = None
        if ciudad:
            where = {"ciudad": {"$eq": ciudad}}

        try:
            results = collection.query(
                query_texts=[query],
                n_results=min(n_results * 2, collection.count() or 1),  # over-fetch para filtrar
                where=where,
                include=["documents", "metadatas", "distances"],
            )
        except Exception as exc:
            log.error("red_medica_search_failed", error=str(exc))
            return []

        hospitals: list[dict[str, Any]] = []
        docs = (results.get("documents") or [[]])[0]
        metas = (results.get("metadatas") or [[]])[0]
        dists = (results.get("distances") or [[]])[0]

        for doc, meta, dist in zip(docs, metas, dists):
            # Filtro por aseguradora en metadata JSON (Chroma no soporta contains en arrays)
            if aseguradora:
                aseg_list: list[str] = json.loads(meta.get("aseguradoras", "[]"))
                if aseguradora.lower() not in [a.lower() for a in aseg_list]:
                    continue

            especialidades: list[str] = json.loads(meta.get("especialidades", "[]"))

            hospitals.append({
                "nombre": meta.get("nombre", ""),
                "ciudad": meta.get("ciudad", ""),
                "aseguradoras": json.loads(meta.get("aseguradoras", "[]")),
                "especialidades": especialidades,
                "latitud": float(meta["latitud"]) if meta.get("latitud") else None,
                "longitud": float(meta["longitud"]) if meta.get("longitud") else None,
                "nota": meta.get("nota", ""),
                "grupo": meta.get("grupo", ""),
                "relevance_score": round(1 - dist, 4),  # cosine: 1=idéntico, 0=irrelevante
                "texto_indexado": doc,
            })

            if len(hospitals) >= n_results:
                break

        log.info(
            "red_medica_search",
            query=query[:60],
            results=len(hospitals),
            ciudad=ciudad,
            aseguradora=aseguradora,
        )
        return hospitals

    def find_by_specialty(
        self,
        specialty: str,
        aseguradora: str | None = None,
        ciudad: str | None = None,
        n_results: int = 5,
    ) -> list[dict[str, Any]]:
        """Búsqueda orientada a especialidad médica específica."""
        query = f"Hospital con especialidad {specialty} para atención médica"
        return self.search(
            query=query,
            n_results=n_results,
            ciudad=ciudad,
            aseguradora=aseguradora,
        )
