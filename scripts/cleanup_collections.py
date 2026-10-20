"""Lista y limpia colecciones RAG antiguas de forma confirmada."""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from storage.vector_store import PersistentVectorStore


def nombre_activo(version: str) -> str:
    sufijo = re.sub(r"[^a-zA-Z0-9_-]", "_", version).strip("_")[:40]
    return f"rag_documents_{sufijo or 'v1'}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path(os.getenv("RAG_DATA_DIR", "data")))
    parser.add_argument("--version", default=os.getenv("RAG_EMBEDDING_VERSION", "gemini-embedding-001:768"))
    parser.add_argument("--confirmar", action="store_true")
    args = parser.parse_args()
    activo = nombre_activo(args.version)
    store = PersistentVectorStore(args.data / "chroma", activo)
    try:
        antiguas = sorted(
            nombre for nombre in store.listar_colecciones()
            if nombre.startswith("rag_documents_") and nombre != activo
        )
        print(f"Colección activa: {activo}")
        print("Colecciones antiguas:")
        for nombre in antiguas:
            print(f"  - {nombre}")
        if not args.confirmar:
            print("No se eliminó nada. Añade --confirmar para borrar las antiguas.")
            return
        for nombre in antiguas:
            store.eliminar_coleccion(nombre)
            print(f"Eliminada: {nombre}")
    finally:
        store.close()


if __name__ == "__main__":
    main()
