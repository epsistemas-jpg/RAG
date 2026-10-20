"""Trabajador incremental de documentos."""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Callable

from rag.carga import cargar_archivo
from rag.embeddings import MODELO_EMBEDDING, embed_documentos
from rag.indice import chunkear, chunkear_con_paginas
from rag.ocr import OcrProvider, extraer_con_ocr
from services.document_service import DocumentService, DocumentoDetectado
from storage.metadata_store import MetadataStore
from storage.vector_store import PersistentVectorStore


@dataclass(frozen=True)
class IndexingReport:
    nuevos: int
    modificados: int
    sin_cambios: int
    eliminados: int
    fallidos: int


class IndexingService:
    """Procesa solo archivos nuevos o que cambiaron."""

    def __init__(
        self,
        corpus,
        metadata: MetadataStore,
        vector_store: PersistentVectorStore,
        embedder: Callable[[list[str]], list[list[float]]] = embed_documentos,
        embedding_version: str = f"{MODELO_EMBEDDING}:768",
        ocr_provider: OcrProvider | None = None,
        batch_size: int | None = None,
    ):
        self.documentos = DocumentService(corpus, metadata)
        self.metadata = metadata
        self.vector_store = vector_store
        self.embedder = embedder
        self.embedding_version = embedding_version
        self.ocr_provider = ocr_provider
        self.batch_size = batch_size or int(os.getenv("RAG_EMBEDDING_BATCH_SIZE", "32"))
        if self.batch_size < 1:
            raise ValueError("batch_size debe ser mayor que cero")

    def ejecutar(self, on_progress: Callable[[int, int], None] | None = None) -> IndexingReport:
        plan = self.documentos.planificar()
        total = len(plan.nuevos) + len(plan.modificados) + len(plan.eliminados) + len(plan.sin_cambios)
        procesados = 0
        if on_progress:
            on_progress(procesados, total)
        for eliminado in plan.eliminados:
            self.vector_store.eliminar_documento(eliminado.document_id)
            self.metadata.eliminar(eliminado.document_id)
            procesados += 1
            if on_progress:
                on_progress(procesados, total)

        fallidos = 0
        for documento in [*plan.nuevos, *plan.modificados]:
            try:
                self._procesar(documento)
            except Exception as error:
                fallidos += 1
                self.metadata.marcar_error(documento.document_id, str(error))
            procesados += 1
            if on_progress:
                on_progress(procesados, total)

        if on_progress:
            on_progress(total, total)

        return IndexingReport(
            nuevos=len(plan.nuevos),
            modificados=len(plan.modificados),
            sin_cambios=len(plan.sin_cambios),
            eliminados=len(plan.eliminados),
            fallidos=fallidos,
        )

    def _procesar(self, documento: DocumentoDetectado) -> None:
        self.documentos.registrar_pendiente(documento, self.embedding_version)
        self.vector_store.eliminar_documento(documento.document_id)
        cargado = cargar_archivo(documento.ruta)
        if cargado.requiere_ocr:
            cargado = type(cargado)(
                texto=extraer_con_ocr(documento.ruta, self.ocr_provider),
                fuente=cargado.fuente,
                formato=cargado.formato,
                paginas=cargado.paginas,
                requiere_ocr=False,
                paginas_texto=None,
                case_id=documento.case_id,
                metadatos=documento.metadatos_caso,
            )
        chunks = (
            chunkear_con_paginas(cargado)
            if cargado.paginas_texto
            else chunkear([cargado])
        )
        ids = [f"{documento.document_id}#{chunk.posicion:03d}" for chunk in chunks]
        for inicio in range(0, len(chunks), self.batch_size):
            lote = chunks[inicio:inicio + self.batch_size]
            metadatos = []
            for chunk in lote:
                metadata = {
                    "document_id": documento.document_id,
                    "fuente": chunk.fuente,
                    "formato": chunk.formato,
                    "posicion": chunk.posicion,
                }
                if chunk.pagina is not None:
                    metadata["pagina"] = chunk.pagina
                if documento.case_id:
                    metadata["case_id"] = documento.case_id
                if documento.metadatos_caso:
                    metadata.update(documento.metadatos_caso)
                metadatos.append(metadata)
            self.vector_store.agregar(
                ids=ids[inicio:inicio + self.batch_size],
                embeddings=self.embedder([chunk.texto for chunk in lote]),
                textos=[chunk.texto for chunk in lote],
                metadatos=metadatos,
            )
        self.metadata.marcar_completado(documento.document_id, len(chunks), cargado.paginas)
