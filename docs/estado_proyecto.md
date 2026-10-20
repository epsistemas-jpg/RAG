# Estado del proyecto

Auditoría frente al prompt de transformación del motor RAG. Estado verificado el
20 de octubre de 2026.

## Terminado

- Motor independiente separado de la CLI original.
- Extracción de Markdown, TXT, PDF y DOCX; preservación de páginas de PDF.
- Indexación completa/incremental mediante `scripts/index_corpus.py`.
- Detección de PDF sin texto y proveedor OCR independiente con Tesseract.
- Chroma persistente y metadatos en SQLite.
- SHA-256, detección de nuevos/modificados/eliminados y actualización idempotente.
- Embeddings por lotes, caché local y versionado de colecciones.
- API FastAPI con health, search, ask, index, jobs y documentos.
- Validación Pydantic, API keys, roles, rate limiting y restricción del corpus.
- Reintento de trabajos fallidos y serialización de indexaciones dentro del proceso.
- Recuperación híbrida BM25 + densa mediante RRF.
- Abstención cuando la evidencia es insuficiente y fuentes con documento/página.
- Métricas Recall@k, MRR y nDCG; conjunto fijo de 8 preguntas.
- Benchmark local de extracción/chunking y backup/restauración con validación de rutas.
- Documentación de API, OCR, ejecución y pruebas.
- Suite automatizada actual: 36 pruebas correctas.

## Parcial o pendiente

1. **Cola de trabajos durable:** actualmente usa `BackgroundTasks` y SQLite; si el
   proceso se apaga durante un trabajo, no existe un worker externo que lo
   recupere automáticamente. Falta un worker persistente o una cola ligera.
2. **Progreso fino:** el estado informa totales al finalizar, pero no actualiza
   progreso por documento/lote durante una indexación larga.
3. **Concurrencia distribuida:** SQLite ya proporciona un lease con expiración
   para impedir dos indexadores simultáneos que compartan la misma base; para
   despliegues separados se recomienda una cola externa.
4. **Excel:** `.xlsx` ya se extrae como filas separadas por `|`; `.xls`, fórmulas
   calculadas y nombres detallados de hoja/celda siguen pendientes.
5. **Imágenes y visión:** OCR cubre PDF escaneado y ahora imágenes comunes
   (`png/jpg/tif`); análisis de diagramas, imágenes incrustadas y tablas visuales
   sigue pendiente.
6. **Tablas PDF:** la extracción nativa no tiene una estrategia específica de
   reconstrucción de tablas.
7. **Evaluación densa/híbrida:** existe la línea base BM25 y el benchmark
   `scripts/evaluate_dense_hybrid.py`; falta ejecutarlo con la clave Gemini del
   entorno final y comparar resultados reales.
8. **Pruebas de integración:** faltan pruebas con un servidor FastAPI real,
   Chroma persistente entre reinicios y un proveedor externo simulado por HTTP.
9. **Despliegue:** existe logging JSON básico, `X-Request-ID`, métricas
   Prometheus básicas y guía de HTTPS/proxy en `deploy/`; la configuración real
   de certificados y secretos depende del entorno final.
10. **Operación del índice:** existen comprobación de consistencia, reconstrucción
    explícita y limpieza confirmada de colecciones antiguas.
11. **Integración externa:** ya existe `integrations/rag_client.py`; queda validar
    el contrato contra una instancia desplegada y versionar cambios futuros.

## Orden recomendado para continuar

1. Añadir comando de consistencia y reconstrucción controlada del índice.
2. Añadir progreso por documento y recuperación de trabajos pendientes.
3. Añadir pruebas de integración persistentes y comparación densa/híbrida.
4. Completar Excel avanzado y posteriormente imágenes según necesidad real.
5. Preparar despliegue productivo y validar el cliente HTTP de integración.

## Verificación ejecutada

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
.\.venv\Scripts\python.exe scripts\benchmark_local.py
.\.venv\Scripts\python.exe scripts\evaluate_retrieval.py
```

