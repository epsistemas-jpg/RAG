"""Arranque productivo con almacenamiento persistente configurado."""

from __future__ import annotations

import os
import re
from pathlib import Path

from dotenv import load_dotenv

from api.main import _claves_configuradas, create_app
from rag.consulta_persistente import ServicioConsultaPersistente
from rag.ocr import TesseractProvider
from services.indexing_service import IndexingService
from storage.job_store import JobStore
from storage.metadata_store import MetadataStore
from storage.vector_store import PersistentVectorStore


def build_app():
    load_dotenv()
    if not os.getenv("RAG_API_KEY") and not _claves_configuradas():
        raise RuntimeError("Configura RAG_API_KEY o RAG_API_KEYS como clave:rol")
    data = Path(os.getenv("RAG_DATA_DIR", "data"))
    corpus = Path(os.getenv("RAG_CORPUS", "corpus"))
    embedding_version = os.getenv("RAG_EMBEDDING_VERSION", "gemini-embedding-001:768")
    sufijo = re.sub(r"[^a-zA-Z0-9_-]", "_", embedding_version).strip("_")[:40]
    coleccion = f"rag_documents_{sufijo or 'v1'}"
    metadata = MetadataStore(data / "metadata.sqlite3")
    vector = PersistentVectorStore(data / "chroma", coleccion=coleccion)
    jobs = JobStore(data / "metadata.sqlite3")
    ocr = TesseractProvider() if os.getenv("RAG_TESSERACT_PATH") or os.name == "nt" else None
    indexador = IndexingService(
        corpus, metadata, vector, embedding_version=embedding_version, ocr_provider=ocr
    )
    hibrido = os.getenv("RAG_HYBRID_SEARCH", "true").lower() not in {"0", "false", "no"}
    consultas = ServicioConsultaPersistente(vector, hibrido=hibrido)
    return create_app(servicio_consulta=consultas, indexador=indexador, jobs=jobs)


app = build_app()
