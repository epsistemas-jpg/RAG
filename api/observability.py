"""Observabilidad mínima sin registrar secretos ni contenido de documentos."""

from __future__ import annotations

import json
import logging
import os
from collections import Counter
from threading import Lock
import time
from uuid import uuid4

from fastapi import Request


class Metrics:
    """Métricas de proceso, sin etiquetas de usuario ni contenido."""

    def __init__(self):
        self._lock = Lock()
        self.requests = Counter()
        self.statuses = Counter()
        self.total_seconds = 0.0

    def observar(self, status: int, segundos: float) -> None:
        with self._lock:
            self.requests["total"] += 1
            self.statuses[str(status)] += 1
            self.total_seconds += segundos

    def prometheus(self) -> str:
        with self._lock:
            lineas = [
                "# TYPE rag_http_requests_total counter",
                f"rag_http_requests_total {self.requests['total']}",
                "# TYPE rag_http_request_status_total counter",
            ]
            lineas.extend(
                f'rag_http_request_status_total{{status="{status}"}} {cantidad}'
                for status, cantidad in sorted(self.statuses.items())
            )
            lineas.extend([
                "# TYPE rag_http_request_duration_seconds_sum counter",
                f"rag_http_request_duration_seconds_sum {self.total_seconds:.6f}",
            ])
            return "\n".join(lineas) + "\n"


def configurar_logging() -> logging.Logger:
    logger = logging.getLogger("rag.api")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
    logger.setLevel(os.getenv("RAG_LOG_LEVEL", "INFO").upper())
    logger.propagate = False
    return logger


def registrar_solicitud(logger: logging.Logger, request: Request, request_id: str, status: int, segundos: float) -> None:
    logger.info(json.dumps({
        "evento": "http_request", "request_id": request_id,
        "metodo": request.method, "ruta": request.url.path,
        "status": status, "duracion_ms": round(segundos * 1000, 2),
    }, ensure_ascii=False))


def nuevo_request_id(request: Request) -> str:
    return request.headers.get("X-Request-ID") or str(uuid4())
