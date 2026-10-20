"""Valida la estructura legal del corpus sin indexar ni llamar a proveedores."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
from services.document_service import DocumentService
from storage.metadata_store import MetadataStore


def main() -> None:
    load_dotenv()
    raiz = Path(os.getenv("RAG_CORPUS", "corpus"))
    if not raiz.is_dir():
        raise SystemExit(f"No existe RAG_CORPUS: {raiz}")
    servicio = DocumentService(raiz, MetadataStore(":memory:"))
    documentos = servicio.descubrir()
    por_caso: dict[str, int] = {}
    sin_metadatos = []
    for documento in documentos:
        if documento.case_id:
            por_caso[documento.case_id] = por_caso.get(documento.case_id, 0) + 1
            if not documento.metadatos_caso:
                sin_metadatos.append(documento.case_id)
    print(json.dumps({
        "corpus": str(raiz),
        "documentos": len(documentos),
        "casos_detectados": por_caso,
        "archivos_fuera_de_carpeta_de_caso": sum(1 for d in documentos if not d.case_id),
        "casos_sin_case_json": sorted(set(sin_metadatos)),
        "listo_para_indexar": bool(documentos) and not sin_metadatos,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
