"""Comprueba la consistencia entre metadatos SQLite y vectores Chroma."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from storage.metadata_store import MetadataStore
from storage.vector_store import PersistentVectorStore


def nombre_coleccion(version: str) -> str:
    sufijo = re.sub(r"[^a-zA-Z0-9_-]", "_", version).strip("_")[:40]
    return f"rag_documents_{sufijo or 'v1'}"


def revisar(data: Path, version: str) -> dict:
    metadata = MetadataStore(data / "metadata.sqlite3")
    vector = PersistentVectorStore(data / "chroma", nombre_coleccion(version))
    try:
        registros = {registro.document_id: registro for registro in metadata.listar()}
        datos = vector.todos()
        ids = datos.get("ids", [])
        metadatos = datos.get("metadatas", [])
        ids_vector = {meta.get("document_id") for meta in metadatos if meta}
        completados = {id_doc for id_doc, registro in registros.items() if registro.estado == "completed"}
        return {
            "coleccion": nombre_coleccion(version),
            "documentos_metadata": len(registros),
            "vectores": len(ids),
            "documentos_sin_vectores": sorted(completados - ids_vector),
            "vectores_sin_metadata": sorted(ids_vector - set(registros)),
            "documentos_fallidos": sorted(
                id_doc for id_doc, registro in registros.items() if registro.estado == "failed"
            ),
            "consistente": not (completados - ids_vector or ids_vector - set(registros)),
        }
    finally:
        vector.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path(os.getenv("RAG_DATA_DIR", "data")))
    parser.add_argument(
        "--version", default=os.getenv("RAG_EMBEDDING_VERSION", "gemini-embedding-001:768")
    )
    args = parser.parse_args()
    print(json.dumps(revisar(args.data, args.version), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
