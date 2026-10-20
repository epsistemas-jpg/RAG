"""Mide extracción y chunking sin llamar a proveedores externos.

Ejemplos:
    python scripts/benchmark_local.py
    python scripts/benchmark_local.py --limite 100
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rag.carga import cargar_archivo
from rag.indice import chunkear


def medir(corpus: Path, limite: int | None = None) -> dict:
    rutas = sorted(
        ruta for ruta in corpus.rglob("*")
        if ruta.is_file() and ruta.suffix.lower() in {".md", ".txt", ".pdf", ".docx", ".xlsx", ".png", ".jpg", ".jpeg", ".tif", ".tiff"}
    )
    if limite is not None:
        rutas = rutas[:limite]

    inicio = time.perf_counter()
    documentos = [cargar_archivo(ruta) for ruta in rutas]
    segundos_extraccion = time.perf_counter() - inicio
    inicio = time.perf_counter()
    chunks = chunkear(documentos)
    segundos_chunking = time.perf_counter() - inicio

    return {
        "documentos": len(documentos),
        "chunks": len(chunks),
        "caracteres": sum(len(documento.texto) for documento in documentos),
        "paginas": sum(documento.paginas or 0 for documento in documentos),
        "segundos_extraccion": round(segundos_extraccion, 4),
        "segundos_chunking": round(segundos_chunking, 4),
        "requieren_ocr": sum(documento.requiere_ocr for documento in documentos),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, default=Path("corpus"))
    parser.add_argument("--limite", type=int, default=None)
    args = parser.parse_args()
    print(json.dumps(medir(args.corpus, args.limite), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
