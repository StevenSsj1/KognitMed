# KognitMed

## Frontend web

El frontend conversacional consume `POST /api/v1/chat` y conserva el
`conversation_id` en el navegador para continuar cada conversacion.

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

4. Abre `http://127.0.0.1:8000`.

La interfaz intenta leer la geolocalizacion al cargar y guarda las coordenadas
en `localStorage` bajo `kognitmed.location`. El navegador controla el permiso
del sistema para esa lectura; en produccion la API de geolocalizacion requiere
un contexto seguro, normalmente HTTPS.
