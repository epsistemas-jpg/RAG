# Arquitectura actual y línea base

Este documento registra la arquitectura observada antes de iniciar la
modularización. Es una línea base, no una especificación de la API futura.

## Flujo actual

```text
corpus/ -> rag.carga -> rag.indice -> rag.embeddings -> Chroma en memoria
                                      \-> BM25 en memoria
                                      -> rag.generacion -> app.py / consola
```

## Componentes actuales

- `app.py` orquesta la carga, construcción del índice, recuperación y respuesta.
- `rag/carga.py` lee Markdown, texto plano y PDF.
- `rag/indice.py` realiza chunking, búsqueda densa con Chroma, BM25 y RRF.
- `rag/embeddings.py` llama a Gemini y mantiene una caché local por SHA-256.
- `rag/generacion.py` construye el prompt, llama a Groq y valida citas.
- `checkpoints/` contiene ejemplos ejecutables y una evaluación golden.

## Límites de la línea base

- La CLI histórica usa `EphemeralClient`; `api/runtime.py` usa Chroma persistente.
- No existe un registro persistente de documentos, versiones o estados.
- La extracción PDF concatena páginas y no conserva referencias de página.
- El proceso de indexación ocurre durante el arranque de la CLI.
- No existe API REST, autenticación, autorización ni cola de trabajos.

La entrada `api/runtime.py` conecta los servicios persistentes: SQLite para
metadatos y trabajos, Chroma persistente para vectores, y el trabajador
incremental. `api/main.py` sigue siendo una fábrica inyectable para pruebas.

## Criterio para la siguiente fase

Las pruebas de `tests/test_characterization.py` cubren el comportamiento local
que debe conservarse durante la modularización: carga del corpus, identidad de
chunks, tokenización, caché de embeddings y validación de citas. No invocan
proveedores externos y deben ejecutarse antes y después de cada cambio
estructural.

## Medición local

`scripts/benchmark_local.py` mide extracción, páginas, chunking y detección de
OCR sin llamar a Gemini ni Groq. Permite ejecutar muestras progresivas:

```powershell
python scripts/benchmark_local.py --limite 100
python scripts/benchmark_local.py --limite 500
python scripts/benchmark_local.py --limite 1000
```

Las métricas offline están en `evaluation/metrics.py`. Reciben identificadores
de chunks o documentos y permiten calcular Recall@k, MRR y nDCG sin llamar al
modelo de generación.

Para OCR real se puede configurar `TesseractProvider` de `rag/ocr.py`. Requiere
los ejecutables `tesseract` y `pdftoppm` en `PATH`; el indexador solo lo invoca
para PDFs sin texto nativo.
