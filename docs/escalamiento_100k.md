# Operación para más de 100.000 PDFs

La indexación es incremental: cada archivo se identifica por hash y solo se
reprocesan archivos nuevos o modificados. Los embeddings se envían por lotes
(`RAG_EMBEDDING_BATCH_SIZE`) y los trabajos pueden ejecutarse fuera del proceso
de la API.

## Configuración recomendada

En `.env`:

```env
RAG_INDEX_MODE=external
RAG_EMBEDDING_BATCH_SIZE=32
RAG_HYBRID_SEARCH=false
RAG_WORKER_WAIT_SECONDS=5
```

`RAG_HYBRID_SEARCH=false` evita cargar todos los textos del corpus en BM25 en
cada proceso de consulta. La búsqueda vectorial y sus filtros siguen activos.

## Flujo operativo

1. Ejecutar `scripts/preflight_escala.py`.
2. Levantar la API; las solicitudes de indexación quedan como trabajos.
3. Ejecutar uno o varios trabajadores controlados con
   `scripts/worker_index.py --once`.
4. Consultar el estado del trabajo y repetir los fallidos.
5. Respaldar `data/metadata.sqlite3` y el almacenamiento vectorial.

Para una operación distribuida real, Chroma debe reemplazarse por un servicio
vectorial administrado o distribuido. El contrato usado por
`PersistentVectorStore` mantiene aislada esa migración de la API y de la
indexación incremental.
