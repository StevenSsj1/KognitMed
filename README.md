# KognitMed

## Frontend Gradio

El frontend conversacional consume `POST /api/v1/chat` y conserva el
`conversation_id` durante la sesion abierta en Gradio.

1. Instala las dependencias:

```powershell
python -m pip install -r requirements.txt
```

2. Crea `.env` desde `.env.example` y configura el proveedor LLM.

Por defecto el backend usa OpenAI, asi que `OPENAI_API_KEY` debe tener valor.
Para usar Gemini, define `LLM_PROVIDER=gemini` y `GEMINI_API_KEY`.

3. Inicia la API FastAPI en `http://127.0.0.1:8000`:

```powershell
python main.py
```

Tambien puedes usar Uvicorn directamente desde la raiz del repositorio:

```powershell
python -m uvicorn --app-dir src kognitmed.main:app --host 127.0.0.1 --port 8000 --reload
```

4. Inicia el frontend:

```powershell
python -m kognitmed.frontend.gradio_app
```

5. Abre `http://127.0.0.1:7860`.

Para apuntar el frontend a otra API, define `KOGNITMED_API_BASE_URL` antes de
iniciarlo.

El boton `Ubicacion` solicita permiso de geolocalizacion al navegador. La
latitud y longitud quedan capturadas en el frontend para la sesion actual. En
produccion, la API de geolocalizacion del navegador requiere un contexto
seguro, normalmente HTTPS, y permiso explicito del usuario.
