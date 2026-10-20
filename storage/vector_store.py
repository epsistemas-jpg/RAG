"""Adaptador pequeño para un índice Chroma persistente."""

from __future__ import annotations

from pathlib import Path

import chromadb
from chromadb.api.shared_system_client import SharedSystemClient


class PersistentVectorStore:
    """Expone operaciones explícitas sobre una colección persistente."""

    def __init__(
        self,
        ruta: str | Path = "data/chroma",
        coleccion: str = "rag_documents_v1",
    ):
        self.ruta = Path(ruta)
        self.ruta.mkdir(parents=True, exist_ok=True)
        self.cliente = chromadb.PersistentClient(path=str(self.ruta))
        self.coleccion = self.cliente.get_or_create_collection(
            name=coleccion,
            embedding_function=None,
            configuration={"hnsw": {"space": "cosine"}},
        )

    def contar(self) -> int:
        return self.coleccion.count()

    def close(self) -> None:
        """Libera los archivos nativos, especialmente en Windows."""
        if getattr(self, "_cerrado", False):
            return
        self._cerrado = True
        cerrar = getattr(self.cliente, "close", None)
        if cerrar is not None:
            try:
                cerrar()
            except AttributeError:
                # Chroma 1.x puede intentar detener dos veces un backend
                # compartido cuando existen dos clientes para la misma ruta.
                pass
        try:
            SharedSystemClient.clear_system_cache()
        except (AttributeError, RuntimeError):
            pass

    def eliminar_documento(self, document_id: str) -> None:
        self.coleccion.delete(where={"document_id": document_id})

    def agregar(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        textos: list[str],
        metadatos: list[dict],
    ) -> None:
        self.coleccion.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=textos,
            metadatas=metadatos,
        )

    def consultar(self, embedding: list[float], k: int = 4, where: dict | None = None) -> dict:
        argumentos = {"query_embeddings": [embedding], "n_results": k}
        if where:
            argumentos["where"] = where
        return self.coleccion.query(**argumentos)

    def todos(self) -> dict:
        """Devuelve texto y metadatos para construir el índice léxico."""
        return self.coleccion.get(include=["documents", "metadatas"])

    def vaciar(self) -> None:
        """Elimina todos los vectores de esta colección."""
        ids = self.coleccion.get(include=[]).get("ids", [])
        if ids:
            self.coleccion.delete(ids=ids)

    def listar_colecciones(self) -> list[str]:
        return [coleccion.name for coleccion in self.cliente.list_collections()]

    def eliminar_coleccion(self, nombre: str) -> None:
        """Elimina una colección explícitamente seleccionada."""
        self.cliente.delete_collection(name=nombre)
