"""Configuración centralizada, sin credenciales ni efectos secundarios."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ConfiguracionRAG:
    """Valores operativos que antes estaban dispersos en la CLI."""

    corpus: Path = Path("corpus")
    top_k: int = 4
    umbral_dominio: float = 0.62
    chunk_size: int = 500
    chunk_overlap: int = 80

    @classmethod
    def desde_entorno(cls) -> "ConfiguracionRAG":
        """Lee configuración opcional; conserva los valores actuales por defecto."""
        return cls(
            corpus=Path(os.getenv("RAG_CORPUS", "corpus")),
            top_k=int(os.getenv("RAG_TOP_K", "4")),
            umbral_dominio=float(os.getenv("RAG_UMBRAL_DOMINIO", "0.62")),
            chunk_size=int(os.getenv("RAG_CHUNK_SIZE", "500")),
            chunk_overlap=int(os.getenv("RAG_CHUNK_OVERLAP", "80")),
        )


def validar_configuracion(configuracion: ConfiguracionRAG) -> None:
    """Rechaza valores que producirían un índice inválido."""
    if configuracion.top_k < 1:
        raise ValueError("top_k debe ser mayor que cero")
    if configuracion.chunk_size < 1:
        raise ValueError("chunk_size debe ser mayor que cero")
    if not 0 <= configuracion.chunk_overlap < configuracion.chunk_size:
        raise ValueError("chunk_overlap debe estar entre cero y chunk_size - 1")
    if not 0 <= configuracion.umbral_dominio <= 1:
        raise ValueError("umbral_dominio debe estar entre cero y uno")
