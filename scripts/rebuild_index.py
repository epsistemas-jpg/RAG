"""Reconstrucción completa y explícita del índice persistente.

La operación requiere `--confirmar` porque elimina los vectores y metadatos
actuales de la colección seleccionada. Para una actualización normal use la
API `/api/v1/index`, que es incremental.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rag.ocr import TesseractProvider
from services.indexing_service import IndexingService
from storage.metadata_store import MetadataStore
from storage.vector_store import PersistentVectorStore


def coleccion(version: str) -> str:
    sufijo = re.sub(r"[^a-zA-Z0-9_-]", "_", version).strip("_")[:40]
    return f"rag_documents_{sufijo or 'v1'}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path(os.getenv("RAG_DATA_DIR", "data")))
    parser.add_argument("--corpus", type=Path, default=Path(os.getenv("RAG_CORPUS", "corpus")))
    parser.add_argument("--version", default=os.getenv("RAG_EMBEDDING_VERSION", "gemini-embedding-001:768"))
    parser.add_argument("--confirmar", action="store_true")
    args = parser.parse_args()
    nombre = coleccion(args.version)
    if not args.confirmar:
        print(f"Reconstrucción no ejecutada. Se limpiaría: {args.data / 'metadata.sqlite3'} y {nombre}")
        print("Añade --confirmar para ejecutar la operación destructiva.")
        raise SystemExit(2)

    metadata = MetadataStore(args.data / "metadata.sqlite3")
    vector = PersistentVectorStore(args.data / "chroma", nombre)
    try:
        vector.vaciar()
        metadata.vaciar()
        ocr = TesseractProvider() if os.name == "nt" else None
        servicio = IndexingService(
            args.corpus, metadata, vector,
            embedding_version=args.version,
            ocr_provider=ocr,
        )
        print(servicio.ejecutar())
    finally:
        vector.close()


if __name__ == "__main__":
    main()
