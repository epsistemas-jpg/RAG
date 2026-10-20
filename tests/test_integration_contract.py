import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.main import create_app


class ContratoIntegracionTests(unittest.TestCase):
    def test_interfaz_local_se_entrega_en_raiz(self):
        respuesta = TestClient(create_app()).get("/")
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("Motor RAG", respuesta.text)

    def test_casos_similares_devuelve_grupos_sin_probabilidad_inventada(self):
        class Servicio:
            def casos_similares(self, pregunta, top_k=10):
                return [{"case_id": "caso-0001", "fuentes": ["sentencia.pdf"], "relevancia": 0.8}]

        cliente = TestClient(create_app(servicio_consulta=Servicio()))
        respuesta = cliente.post(
            "/api/v1/similar-cases",
            json={"pregunta": "hechos parecidos", "top_k": 5},
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json()["casos"][0]["case_id"], "caso-0001")
        self.assertIsNone(respuesta.json()["probabilidad"])
        self.assertTrue(respuesta.json()["advertencias"])

    def test_roles_restringen_indexacion_y_consulta_sigue_disponible(self):
        class Servicio:
            def buscar(self, pregunta):
                return []

        with patch.dict(os.environ, {"RAG_API_KEYS": "solo-consulta:consulta"}, clear=False):
            cliente = TestClient(create_app(servicio_consulta=Servicio(), indexador=object()))
            headers = {"X-API-Key": "solo-consulta"}
            self.assertEqual(cliente.post("/api/v1/search", json={"pregunta": "hola"}, headers=headers).status_code, 200)
            self.assertEqual(cliente.post("/api/v1/index", json={}, headers=headers).status_code, 403)

    def test_clave_incorrecta_devuelve_401(self):
        with patch.dict(os.environ, {"RAG_API_KEY": "secreta", "RAG_API_KEYS": ""}, clear=False):
            cliente = TestClient(create_app())
            respuesta = cliente.get("/api/v1/jobs/no-existe", headers={"X-API-Key": "incorrecta"})
            self.assertEqual(respuesta.status_code, 401)

    def test_metricas_no_exponen_contenido_y_tienen_formato_prometheus(self):
        cliente = TestClient(create_app())
        cliente.get("/api/v1/health")
        respuesta = cliente.get("/api/v1/metrics")
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("rag_http_requests_total", respuesta.text)
        self.assertNotIn("pregunta", respuesta.text.lower())

    def test_error_interno_tiene_contrato_sin_traza(self):
        class ServicioRoto:
            def buscar(self, pregunta):
                raise RuntimeError("detalle privado")

        cliente = TestClient(create_app(servicio_consulta=ServicioRoto()), raise_server_exceptions=False)
        respuesta = cliente.post("/api/v1/search", json={"pregunta": "hola"})
        self.assertEqual(respuesta.status_code, 500)
        self.assertEqual(respuesta.json()["error"], "internal_error")
        self.assertNotIn("detalle privado", respuesta.text)
