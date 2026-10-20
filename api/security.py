"""Controles de seguridad locales para la API."""

from __future__ import annotations

import os
import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import HTTPException, Request, status


class RateLimiter:
    """Limitador sencillo por cliente; en despliegues distribuidos usar Redis."""

    def __init__(self, limite: int | None = None, ventana: int = 60):
        self.limite = limite if limite is not None else int(os.getenv("RAG_RATE_LIMIT", "60"))
        self.ventana = ventana
        self._eventos: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def verificar(self, request: Request) -> None:
        if self.limite <= 0:
            return
        cliente = request.client.host if request.client else "unknown"
        ahora = time.monotonic()
        with self._lock:
            eventos = self._eventos[cliente]
            while eventos and ahora - eventos[0] >= self.ventana:
                eventos.popleft()
            if len(eventos) >= self.limite:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Límite de solicitudes excedido",
                    headers={"Retry-After": str(self.ventana)},
                )
            eventos.append(ahora)
