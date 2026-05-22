# MediOrientador Agents (3-Layer RAG)

Este folder contiene la implementacion canonica del pipeline RAG de MediOrientador.

## Capas

1. `intake_agent.py`
- Normalizacion y validacion de input.
- Deteccion heuristica temprana de emergencia.
- No usa LLM.

2. `reasoning_agent.py`
- Cruce entre sintomas (extraidos por LLM), cobertura y red medica.
- Consulta a ChromaDB via `RedMedicaSearchService`.
- No usa LLM.

3. `response_agent.py`
- Sintesis final en lenguaje natural para el paciente.
- Usa LLM para respuesta conversacional.
- Mantiene salida estructurada (`OrientationResponse`).

## Patron de diseno

- `service.py` es el orquestador (application service).
- Cada agent tiene una responsabilidad unica (single responsibility).
- Se mantiene compatibilidad hacia atras con `intake.py`, `matcher.py`, `output.py` via aliases.

## Convenciones

- Determinismo y reglas explicitas en Intake/Reasoning.
- LLM solo en puntos necesarios (extraccion y sintesis).
- Fallback seguro cuando falla parsing o retrieval.
