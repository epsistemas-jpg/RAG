"""Cliente HTTP mínimo para integrar el motor RAG desde otro sistema."""

from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class RAGClientError(RuntimeError):
    """Error de transporte o respuesta no exitosa del motor RAG."""


@dataclass
class RAGClient:
    base_url: str
    api_key: str
    timeout: float = 30.0

    def _request(self, method: str, path: str, body: dict | None = None) -> dict:
        datos = None if body is None else json.dumps(body).encode("utf-8")
        request = Request(
            self.base_url.rstrip("/") + path, data=datos, method=method,
            headers={"Accept": "application/json", "Content-Type": "application/json", "X-API-Key": self.api_key},
        )
        try:
            with urlopen(request, timeout=self.timeout) as respuesta:
                contenido = respuesta.read().decode("utf-8")
                return json.loads(contenido) if contenido else {}
        except (HTTPError, URLError, TimeoutError) as error:
            detalle = getattr(error, "read", lambda: b"")()
            try:
                mensaje = json.loads(detalle.decode("utf-8")).get("detail", str(error))
            except (AttributeError, json.JSONDecodeError, UnicodeDecodeError):
                mensaje = str(error)
            raise RAGClientError(f"Error RAG {getattr(error, 'code', '')}: {mensaje}") from error

    def health(self) -> dict:
        return self._request("GET", "/api/v1/health")

    def search(self, pregunta: str, top_k: int = 4) -> dict:
        return self._request("POST", "/api/v1/search", {"pregunta": pregunta, "top_k": top_k})

    def ask(self, pregunta: str, top_k: int = 4) -> dict:
        return self._request("POST", "/api/v1/ask", {"pregunta": pregunta, "top_k": top_k})

    def similar_cases(self, pregunta: str, top_k: int = 10) -> dict:
        return self._request("POST", "/api/v1/similar-cases", {"pregunta": pregunta, "top_k": top_k})

    def similar_cases_from_description(self, descripcion_caso: str, top_k: int = 10, **filtros) -> dict:
        """Busca expedientes similares usando el texto escrito por la persona."""
        body = {"descripcion_caso": descripcion_caso, "top_k": top_k, **filtros}
        return self._request("POST", "/api/v1/similar-cases", body)

    def index(self) -> dict:
        return self._request("POST", "/api/v1/index", {})

    def job(self, job_id: str) -> dict:
        return self._request("GET", f"/api/v1/jobs/{job_id}")

    def document(self, document_id: str) -> dict:
        return self._request("GET", f"/api/v1/documents/{document_id}")
