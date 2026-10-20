# API REST

El arranque productivo usa almacenamiento persistente:

```powershell
$env:RAG_API_KEY = "clave-de-desarrollo"
.\.venv\Scripts\uvicorn.exe api.runtime:app --host 127.0.0.1 --port 8000
```

En Windows también puedes crear `.env` y ejecutar `scripts\start_api.cmd` desde
`cmd.exe`, o `scripts\start_api.ps1` desde PowerShell. El arranque muestra la
URL de Swagger y no requiere escribir la variable manualmente en cada sesión.

La documentación OpenAPI queda disponible en `/docs`.
La interfaz local de prueba queda disponible en `/` y no sustituye al frontend
empresarial.

Endpoints principales:

```text
GET    /api/v1/health
GET    /api/v1/metrics
POST   /api/v1/search
POST   /api/v1/ask
POST   /api/v1/similar-cases
POST   /api/v1/index
GET    /api/v1/jobs/{job_id}
POST   /api/v1/jobs/{job_id}/retry
GET    /api/v1/documents/{document_id}
DELETE /api/v1/documents/{document_id}
```

Para operaciones protegidas se envía:

```http
X-API-Key: clave-de-desarrollo
```

Para separar permisos por cliente puede usarse `RAG_API_KEYS` con el formato
`clave:rol,clave:rol`. Los roles admitidos son `consulta`, `indexer` y `admin`.
Consulta permite `/search`, `/ask` y lectura de documentos; `indexer` agrega
indexación y eliminación; `admin` permite todo.

El endpoint de indexación nunca acepta rutas de archivos proporcionadas por el
cliente. Usa exclusivamente el corpus configurado mediante `RAG_CORPUS`.
Los trabajos fallidos pueden reintentarse con `POST /api/v1/jobs/{job_id}/retry`.
Las ejecuciones de indexación se serializan para evitar conflictos entre trabajadores.
El almacenamiento SQLite mantiene un lease con expiración para impedir que dos
procesos compartidos indexen simultáneamente.
`/api/v1/similar-cases` agrupa evidencia por `case_id`; no devuelve una
probabilidad de ganar hasta contar con resultados históricos etiquetados.
El software empresarial puede enviar el texto escrito por la persona como
`descripcion_caso` en lugar de `pregunta`:

```json
{"descripcion_caso":"El usuario demanda por incumplimiento de contrato de servicios", "top_k":10}
```
La API usa ese texto como consulta semántica y devuelve los expedientes
similares y sus fuentes.
El tamaño de lote de embeddings se controla con `RAG_EMBEDDING_BATCH_SIZE` (32 por defecto).
`RAG_EMBEDDING_VERSION` identifica la colección persistente; al cambiar el modelo
o la dimensión se crea otra colección y se debe ejecutar una indexación completa.
Los errores internos responden con `error=internal_error` y `request_id`; las
trazas no se exponen al cliente.

Para revisar si SQLite y Chroma están alineados:

```powershell
.\.venv\Scripts\python.exe scripts\check_index.py
```

Para reconstruir desde cero, primero ejecuta sin confirmación para revisar el
objetivo y luego añade `--confirmar`:

```powershell
.\.venv\Scripts\python.exe scripts\rebuild_index.py
.\.venv\Scripts\python.exe scripts\rebuild_index.py --confirmar
```

La reconstrucción borra únicamente la colección versionada y el registro SQLite
configurados; la indexación normal no requiere este comando.

Para listar o limpiar colecciones de versiones anteriores:

```powershell
.\.venv\Scripts\python.exe scripts\cleanup_collections.py
.\.venv\Scripts\python.exe scripts\cleanup_collections.py --confirmar
```

El segundo comando conserva la colección indicada por `RAG_EMBEDDING_VERSION`.

Para trabajos recuperables tras reinicios, configura `RAG_INDEX_MODE=external` y
ejecuta `.\.venv\Scripts\python.exe scripts\worker_index.py`. El worker reclama
los trabajos pendientes de forma atómica y actualiza `procesados`/`total` por documento.

## Cliente HTTP

El software empresarial puede usar `integrations.rag_client.RAGClient` sin
importar el motor interno:

```python
from integrations.rag_client import RAGClient

cliente = RAGClient("http://127.0.0.1:8000", "clave-local")
resultado = cliente.ask("¿Cuál es la calificación mínima de NBL-204?")
```

Las respuestas incluyen `X-Request-ID`. Los logs registran método, ruta, estado
y duración, pero no preguntas, claves ni contenido documental.
`/api/v1/metrics` devuelve contadores Prometheus básicos y requiere autenticación.

## Evaluación local

El conjunto `evaluation/preguntas.json` contiene preguntas y documentos esperados.
La línea base BM25 se ejecuta sin claves externas:

```powershell
.\.venv\Scripts\python.exe scripts/evaluate_retrieval.py
```

Con `GEMINI_API_KEY` configurada, la comparación entre BM25, búsqueda densa y
híbrida se ejecuta con:

```powershell
.\.venv\Scripts\python.exe scripts/evaluate_dense_hybrid.py
```

## Backup y restauración

El backup incluye SQLite y Chroma persistente:

```powershell
python scripts/backup.py crear data backups\rag-2026-10-20.zip
python scripts/backup.py restaurar backups\rag-2026-10-20.zip data-restaurada
```

La restauración valida que ninguna entrada del ZIP escape del directorio de
destino.

## Prueba pública en Render

El archivo `render.yaml` prepara un Web Service de demostración. En Render se
debe configurar manualmente `GEMINI_API_KEY`; `RAG_API_KEY` se genera
automáticamente. El servicio usa `scripts/start_render.py` para indexar el
corpus pequeño incluido antes de abrir FastAPI.

El plan gratuito es solo para presentación: el servicio puede dormir tras 15
minutos sin tráfico y no conserva el filesystem local. Para casos reales se
necesita almacenamiento persistente o externo y un worker separado.
