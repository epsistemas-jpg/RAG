"""Indexa el corpus configurado y muestra un reporte operativo."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

from rag.ocr import TesseractProvider
from services.indexing_service import IndexingService
from storage.metadata_store import MetadataStore
from storage.vector_store import PersistentVectorStore


def main() -> None:
    load_dotenv()
    if not os.getenv("GEMINI_API_KEY"):
        raise SystemExit("Falta GEMINI_API_KEY; la indexación vectorial requiere embeddings")
    corpus = Path(os.getenv("RAG_CORPUS", "corpus"))
    data = Path(os.getenv("RAG_DATA_DIR", "data"))
    version = os.getenv("RAG_EMBEDDING_VERSION", "gemini-embedding-001:768")
    coleccion = "rag_documents_" + "".join(c if c.isalnum() or c in "_-" else "_" for c in version)[:40]
    metadata = MetadataStore(data / "metadata.sqlite3")
    vector = PersistentVectorStore(data / "chroma", coleccion)
    try:
        servicio = IndexingService(
            corpus, metadata, vector, embedding_version=version,
            ocr_provider=TesseractProvider() if os.name == "nt" else None,
        )
        reporte = servicio.ejecutar()
        print(json.dumps({
            "corpus": str(corpus), "coleccion": coleccion,
            "reporte": reporte.__dict__, "vectores_totales": vector.contar(),
        }, ensure_ascii=False, indent=2))
    finally:
        vector.close()


if __name__ == "__main__":
    main()
