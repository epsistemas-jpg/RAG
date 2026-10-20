"""Inspección barata del corpus antes de indexaciones masivas."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
from services.document_service import EXTENSIONES_ADMITIDAS


def main() -> None:
    load_dotenv()
    raiz = Path(os.getenv("RAG_CORPUS", "corpus"))
    archivos = [
        ruta for ruta in raiz.rglob("*")
        if ruta.is_file() and ruta.suffix.lower() in EXTENSIONES_ADMITIDAS
    ]
    tamanos = sum(ruta.stat().st_size for ruta in archivos)
    por_extension: dict[str, int] = {}
    for ruta in archivos:
        extension = ruta.suffix.lower() or "[sin_extension]"
        por_extension[extension] = por_extension.get(extension, 0) + 1
    print(json.dumps({
        "corpus": str(raiz.resolve()),
        "archivos": len(archivos),
        "tamano_bytes": tamanos,
        "tamano_gb": round(tamanos / (1024 ** 3), 3),
        "por_extension": dict(sorted(por_extension.items())),
        "batch_embeddings": int(os.getenv("RAG_EMBEDDING_BATCH_SIZE", "32")),
        "modo_indexacion": os.getenv("RAG_INDEX_MODE", "inline"),
        "busqueda_hibrida": os.getenv("RAG_HYBRID_SEARCH", "true"),
        "recomendacion": (
            "usar RAG_INDEX_MODE=external y RAG_HYBRID_SEARCH=false "
            "si el corpus supera 100000 archivos"
        ),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
