"""Pruebas de caracterización del pipeline actual.

Estas pruebas describen el comportamiento existente antes de modularizarlo.
No hacen llamadas de red ni requieren claves de proveedores externos.
Ejecutar desde la raíz con:

    .venv\Scripts\python.exe -m unittest discover -s tests -v
"""

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rag.carga import cargar_archivo, cargar_corpus
from rag.configuracion import ConfiguracionRAG, validar_configuracion
from rag.embeddings import _llave_cache, similitud_coseno
from rag.generacion import citas_validas, extraer_citas, formatear_contexto
from rag.indice import Chunk, Resultado, chunkear, chunkear_con_paginas, tokenizar
from rag.servicios import ServicioIndexacion
from storage.metadata_store import DocumentoRegistro, MetadataStore
from storage.vector_store import PersistentVectorStore
from services.document_service import DocumentService
from services.indexing_service import IndexingService
from api.main import create_app
from fastapi.testclient import TestClient
from rag.servicios import RespuestaConsulta
from rag.consulta_persistente import ServicioConsultaPersistente
from rag.ocr import TesseractProvider, extraer_con_ocr
from api.security import RateLimiter
from evaluation.metrics import ndcg_at_k, recall_at_k, reciprocal_rank
from scripts.backup import crear_backup, restaurar_backup
from storage.job_store import JobStore


class CargaYChunkingCaracterizacionTests(unittest.TestCase):
    def setUp(self):
        self.documentos = cargar_corpus(ROOT / "corpus")

    def test_carga_el_corpus_y_conserva_los_formatos(self):
        self.assertEqual(len(self.documentos), 14)
        formatos = {documento.formato for documento in self.documentos}
        self.assertEqual(formatos, {"md", "txt", "pdf"})
        self.assertTrue(all(documento.fuente for documento in self.documentos))

    def test_chunking_produce_ids_estables_y_metadatos_de_origen(self):
        chunks = chunkear(self.documentos)

        self.assertGreater(len(chunks), len(self.documentos))
        self.assertEqual(chunks[0].id, f"{chunks[0].fuente}#000")
        self.assertEqual(chunks[0].posicion, 0)
        self.assertIn(chunks[0].formato, {"md", "txt", "pdf"})

    def test_chunking_vuelve_a_producir_la_misma_identidad(self):
        primera = [(chunk.id, chunk.texto) for chunk in chunkear(self.documentos)]
        segunda = [(chunk.id, chunk.texto) for chunk in chunkear(self.documentos)]

        self.assertEqual(primera, segunda)

    def test_extrae_docx_con_parrafos_y_tablas(self):
        contenido = """<?xml version="1.0" encoding="UTF-8"?>
        <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:body>
            <w:p><w:r><w:t>Párrafo</w:t></w:r></w:p>
            <w:tbl><w:tr><w:tc><w:p><w:r><w:t>Celda</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
          </w:body>
        </w:document>""".encode("utf-8")
        with tempfile.TemporaryDirectory() as directorio:
            ruta = Path(directorio) / "prueba.docx"
            with ZipFile(ruta, "w") as archivo:
                archivo.writestr("word/document.xml", contenido)
            documento = cargar_corpus(Path(directorio))[0]

        self.assertEqual(documento.formato, "docx")
        self.assertIn("Párrafo", documento.texto)
        self.assertIn("Celda", documento.texto)

    def test_extrae_xlsx_como_filas_de_texto(self):
        shared = b'''<?xml version="1.0"?><sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><si><t>Clave</t></si><si><t>NBL-204</t></si></sst>'''
        sheet = b'''<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row></sheetData></worksheet>'''
        with tempfile.TemporaryDirectory() as directorio:
            ruta = Path(directorio) / "prueba.xlsx"
            with ZipFile(ruta, "w") as archivo:
                archivo.writestr("xl/sharedStrings.xml", shared)
                archivo.writestr("xl/worksheets/sheet1.xml", sheet)
            documento = cargar_corpus(Path(directorio))[0]

        self.assertEqual(documento.formato, "xlsx")
        self.assertIn("Clave | NBL-204", documento.texto)

    def test_pdf_registra_numero_de_paginas_y_no_requiere_ocr(self):
        documento = next(d for d in self.documentos if d.formato == "pdf")

        self.assertIsNotNone(documento.paginas)
        self.assertGreater(documento.paginas, 0)
        self.assertFalse(documento.requiere_ocr)

    def test_imagen_se_marca_para_ocr(self):
        with tempfile.TemporaryDirectory() as directorio:
            ruta = Path(directorio) / "captura.png"
            ruta.write_bytes(b"imagen de prueba")
            documento = cargar_archivo(ruta)
        self.assertEqual(documento.formato, "png")
        self.assertTrue(documento.requiere_ocr)
        self.assertEqual(documento.paginas, 1)

    def test_chunking_de_pdf_conserva_la_pagina(self):
        documento = next(d for d in self.documentos if d.formato == "pdf")
        chunks = chunkear_con_paginas(documento)

        self.assertTrue(chunks)
        self.assertIsNotNone(chunks[0].pagina)


class RecuperacionYGeneracionCaracterizacionTests(unittest.TestCase):
    def test_tokenizacion_normaliza_acentos_y_codigos(self):
        self.assertEqual(tokenizar("Recuperación NBL-204"), ["recuperacion", "nbl", "204"])

    def test_similitud_coseno_de_vectores_identicos(self):
        self.assertAlmostEqual(similitud_coseno([1.0, 2.0], [1.0, 2.0]), 1.0)

    def test_cache_separa_documentos_de_consultas(self):
        documento = _llave_cache("mismo texto", "RETRIEVAL_DOCUMENT")
        consulta = _llave_cache("mismo texto", "RETRIEVAL_QUERY")

        self.assertNotEqual(documento, consulta)

    def test_citas_solo_aceptan_fuentes_recuperadas(self):
        resultados = [
            Resultado(
                chunk=Chunk(
                    id="guia.md#000",
                    texto="Contenido",
                    fuente="guia.md",
                    formato="md",
                    posicion=0,
                )
            )
        ]
        respuesta = "Dato válido [guia.md]. Dato no válido [secreto.md]."

        self.assertEqual(extraer_citas(respuesta), ["guia.md", "secreto.md"])
        self.assertEqual(citas_validas(respuesta, resultados), ["guia.md"])

    def test_contexto_etiqueta_la_fuente(self):
        resultado = Resultado(
            chunk=Chunk(
                id="guia.md#000",
                texto="Contenido de prueba",
                fuente="guia.md",
                formato="md",
                posicion=0,
            )
        )

        contexto = formatear_contexto([resultado])

        self.assertIn("fuente: [guia.md]", contexto)
        self.assertIn("Contenido de prueba", contexto)


class ConfiguracionYServiciosTests(unittest.TestCase):
    def test_configuracion_conserva_los_valores_actuales(self):
        configuracion = ConfiguracionRAG()

        validar_configuracion(configuracion)
        self.assertEqual(configuracion.top_k, 4)
        self.assertEqual(configuracion.chunk_size, 500)
        self.assertEqual(configuracion.chunk_overlap, 80)

    def test_configuracion_rechaza_solapamiento_invalido(self):
        with self.assertRaises(ValueError):
            validar_configuracion(ConfiguracionRAG(chunk_size=10, chunk_overlap=10))

    def test_servicio_de_indexacion_reutiliza_la_carga_existente(self):
        servicio = ServicioIndexacion(ConfiguracionRAG(corpus=ROOT / "corpus"))

        documentos = servicio.cargar_documentos()

        self.assertEqual(len(documentos), 14)


class MetadataStoreTests(unittest.TestCase):
    def test_registro_documental_sobrevive_a_una_nueva_instancia(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directorio:
            ruta = Path(directorio) / "metadata.sqlite3"
            registro = DocumentoRegistro(
                document_id="doc-1",
                ruta="corpus/guia.md",
                nombre="guia.md",
                extension=".md",
                hash_sha256="abc123",
                tamano_bytes=42,
                fecha_modificacion=123.0,
                version_embeddings="gemini-embedding-001:768",
            )

            MetadataStore(ruta).upsert(registro)
            recuperado = MetadataStore(ruta).obtener("doc-1")

            self.assertEqual(recuperado, registro)

    def test_estado_completado_y_error_quedan_registrados(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directorio:
            store = MetadataStore(Path(directorio) / "metadata.sqlite3")
            registro = DocumentoRegistro(
                document_id="doc-2",
                ruta="corpus/a.txt",
                nombre="a.txt",
                extension=".txt",
                hash_sha256="def456",
                tamano_bytes=10,
                fecha_modificacion=456.0,
            )
            store.upsert(registro)

            store.marcar_completado("doc-2", fragmentos=3, paginas=1)
            completado = store.obtener("doc-2")
            self.assertEqual(completado.estado, "completed")
            self.assertEqual(completado.fragmentos, 3)

            store.marcar_error("doc-2", "fallo de prueba")
            fallido = store.obtener("doc-2")
            self.assertEqual(fallido.estado, "failed")
            self.assertEqual(fallido.mensaje_error, "fallo de prueba")


class IndexacionIncrementalTests(unittest.TestCase):
    def test_detecta_nuevo_sin_reprocesar_archivo_igual(self):
        with tempfile.TemporaryDirectory() as directorio:
            raiz = Path(directorio) / "corpus"
            raiz.mkdir()
            archivo = raiz / "a.txt"
            archivo.write_text("contenido", encoding="utf-8")
            store = MetadataStore(Path(directorio) / "metadata.sqlite3")
            servicio = DocumentService(raiz, store, extensiones={".txt"})

            primer_plan = servicio.planificar()
            self.assertEqual(len(primer_plan.nuevos), 1)
            self.assertEqual(len(primer_plan.sin_cambios), 0)

            servicio.registrar_pendiente(primer_plan.nuevos[0], "modelo:1")
            segundo_plan = servicio.planificar()
            self.assertEqual(len(segundo_plan.sin_cambios), 0)
            self.assertEqual(len(segundo_plan.modificados), 1)

            store.marcar_completado(primer_plan.nuevos[0].document_id, fragmentos=1)
            tercer_plan = servicio.planificar()
            self.assertEqual(len(tercer_plan.sin_cambios), 1)

    def test_detecta_modificacion_y_eliminacion(self):
        with tempfile.TemporaryDirectory() as directorio:
            raiz = Path(directorio) / "corpus"
            raiz.mkdir()
            archivo = raiz / "a.txt"
            archivo.write_text("uno", encoding="utf-8")
            store = MetadataStore(Path(directorio) / "metadata.sqlite3")
            servicio = DocumentService(raiz, store, extensiones={".txt"})
            documento = servicio.descubrir()[0]
            servicio.registrar_pendiente(documento, "modelo:1")
            store.marcar_completado(documento.document_id, fragmentos=1)

            archivo.write_text("dos", encoding="utf-8")
            plan_modificado = servicio.planificar()
            self.assertEqual(len(plan_modificado.modificados), 1)

            archivo.unlink()
            plan_eliminado = servicio.planificar()
            self.assertEqual(len(plan_eliminado.eliminados), 1)

    def test_deriva_case_id_de_la_carpeta_del_expediente(self):
        with tempfile.TemporaryDirectory() as directorio:
            raiz = Path(directorio) / "expedientes"
            (raiz / "caso-0001").mkdir(parents=True)
            (raiz / "caso-0001" / "sentencia.pdf").write_bytes(b"pdf")
            store = MetadataStore(Path(directorio) / "metadata.sqlite3")
            documento = DocumentService(raiz, store).descubrir()[0]
            self.assertEqual(documento.case_id, "caso-0001")


class PersistentVectorStoreTests(unittest.TestCase):
    def test_coleccion_persistente_sobrevive_a_una_nueva_instancia(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directorio:
            ruta = Path(directorio) / "chroma"
            store = PersistentVectorStore(ruta, coleccion="test_collection")
            store.agregar(
                ids=["doc-1#000"],
                embeddings=[[1.0, 0.0, 0.0]],
                textos=["texto"],
                metadatos=[{"document_id": "doc-1", "fuente": "a.txt"}],
            )
            self.assertEqual(store.contar(), 1)

            reiniciado = PersistentVectorStore(ruta, coleccion="test_collection")
            self.assertEqual(reiniciado.contar(), 1)
            reiniciado.eliminar_documento("doc-1")
            self.assertEqual(reiniciado.contar(), 0)
            reiniciado.close()
            store.close()


class ApiCaracterizacionTests(unittest.TestCase):
    def test_health_no_construye_el_indice_al_importar(self):
        cliente = TestClient(create_app())

        respuesta = cliente.get("/api/v1/health")

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json(), {"estado": "ok", "indice_disponible": False})

    def test_search_rechaza_servicio_no_disponible(self):
        cliente = TestClient(create_app())

        respuesta = cliente.post(
            "/api/v1/search",
            json={"pregunta": "¿Qué dice el corpus?"},
        )

        self.assertEqual(respuesta.status_code, 503)

    def test_ask_expone_fuentes_y_advertencia_de_abstencion(self):
        class ServicioFalso:
            def responder(self, pregunta):
                return RespuestaConsulta(
                    pregunta=pregunta,
                    respuesta=None,
                    resultados=[],
                    citas=[],
                    similitud_mejor=0.2,
                    abstencion=True,
                )

        cliente = TestClient(create_app(ServicioFalso()))
        respuesta = cliente.post(
            "/api/v1/ask",
            json={"pregunta": "Pregunta fuera del corpus"},
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertIsNone(respuesta.json()["respuesta"])
        self.assertTrue(respuesta.json()["advertencias"])

    def test_index_crea_y_completa_un_trabajo(self):
        class IndexadorFalso:
            def ejecutar(self):
                return type(
                    "Reporte",
                    (),
                    {"nuevos": 1, "modificados": 0, "eliminados": 0,
                     "sin_cambios": 0, "fallidos": 0},
                )()

        with tempfile.TemporaryDirectory() as directorio:
            jobs = JobStore(Path(directorio) / "jobs.sqlite3")
            cliente = TestClient(create_app(indexador=IndexadorFalso(), jobs=jobs))

            creado = cliente.post("/api/v1/index", json={})
            job_id = creado.json()["job_id"]
            estado = cliente.get(f"/api/v1/jobs/{job_id}")

            self.assertEqual(creado.status_code, 202)
            self.assertEqual(estado.status_code, 200)
            self.assertEqual(estado.json()["estado"], "completed")

    def test_delete_retira_documento_y_vector(self):
        class IndexadorFalso:
            def __init__(self, metadata):
                self.metadata = metadata
                self.vector_store = type("Vector", (), {"eliminar_documento": lambda *_: None})()

        with tempfile.TemporaryDirectory() as directorio:
            metadata = MetadataStore(Path(directorio) / "metadata.sqlite3")
            metadata.upsert(DocumentoRegistro(
                document_id="doc-delete", ruta="a.txt", nombre="a.txt", extension=".txt",
                hash_sha256="x", tamano_bytes=1, fecha_modificacion=1.0,
            ))
            cliente = TestClient(create_app(indexador=IndexadorFalso(metadata)))
            respuesta = cliente.delete("/api/v1/documents/doc-delete")
            self.assertEqual(respuesta.status_code, 204)
            self.assertIsNone(metadata.obtener("doc-delete"))

    def test_get_document_devuelve_metadatos_sin_exponer_la_ruta(self):
        class IndexadorFalso:
            def __init__(self, metadata):
                self.metadata = metadata

        with tempfile.TemporaryDirectory() as directorio:
            metadata = MetadataStore(Path(directorio) / "metadata.sqlite3")
            metadata.upsert(DocumentoRegistro(
                document_id="doc-get", ruta="C:/privado/a.txt", nombre="a.txt",
                extension=".txt", hash_sha256="hash", tamano_bytes=10,
                fecha_modificacion=2.0, estado="completed", fragmentos=2,
            ))
            cliente = TestClient(create_app(indexador=IndexadorFalso(metadata)))
            respuesta = cliente.get("/api/v1/documents/doc-get")
            cuerpo = respuesta.json()
            self.assertEqual(respuesta.status_code, 200)
            self.assertEqual(cuerpo["nombre"], "a.txt")
            self.assertNotIn("ruta", cuerpo)

    def test_rate_limiter_responde_429_al_superar_el_limite(self):
        app = create_app()
        app.state.rate_limiter = RateLimiter(limite=1, ventana=60)
        cliente = TestClient(app)

        self.assertEqual(cliente.get("/api/v1/documents/no-existe").status_code, 503)
        segunda = cliente.get("/api/v1/documents/no-existe")

        self.assertEqual(segunda.status_code, 429)


class IndexingServiceTests(unittest.TestCase):
    def test_procesa_nuevo_y_omite_el_siguiente_reintento(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directorio:
            raiz = Path(directorio) / "corpus"
            raiz.mkdir()
            (raiz / "a.txt").write_text("contenido de prueba", encoding="utf-8")
            db = Path(directorio) / "metadata.sqlite3"
            metadata = MetadataStore(db)
            vector = PersistentVectorStore(Path(directorio) / "chroma", "jobs_test")
            llamadas = []

            def embedder(textos):
                llamadas.append(textos)
                return [[1.0, 0.0, 0.0] for _ in textos]

            servicio = IndexingService(raiz, metadata, vector, embedder=embedder)
            primero = servicio.ejecutar()
            segundo = servicio.ejecutar()

            self.assertEqual(primero.nuevos, 1)
            self.assertEqual(primero.fallidos, 0)
            self.assertEqual(segundo.sin_cambios, 1)
            self.assertEqual(len(llamadas), 1)
            self.assertEqual(vector.contar(), 1)
            vector.close()

    def test_indexacion_envia_embeddings_en_lotes_configurables(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directorio:
            raiz = Path(directorio) / "corpus"
            raiz.mkdir()
            (raiz / "a.txt").write_text("palabra " * 180, encoding="utf-8")
            metadata = MetadataStore(Path(directorio) / "metadata.sqlite3")
            vector = PersistentVectorStore(Path(directorio) / "chroma", "batch_test")
            llamadas = []

            def embedder(textos):
                llamadas.append(len(textos))
                return [[1.0, 0.0, 0.0] for _ in textos]

            servicio = IndexingService(
                raiz, metadata, vector, embedder=embedder, batch_size=1
            )
            reporte = servicio.ejecutar()

            self.assertEqual(reporte.fallidos, 0)
            self.assertGreater(len(llamadas), 1)
            self.assertTrue(all(tamano == 1 for tamano in llamadas))
            vector.close()


class PersistentQueryTests(unittest.TestCase):
    def test_reconstruye_fuentes_desde_metadatos_del_vector(self):
        class VectorFalso:
            def consultar(self, embedding, k):
                return {
                    "ids": [["doc-1#000"]],
                    "distances": [[0.1]],
                    "documents": [["evidencia"]],
                    "metadatas": [[{"fuente": "a.txt", "formato": "txt", "posicion": 0}]],
                }

        servicio = ServicioConsultaPersistente(VectorFalso())
        with patch("rag.consulta_persistente.embed_pregunta", return_value=[1.0]):
            resultados = servicio.buscar("pregunta")

        self.assertEqual(resultados[0].chunk.fuente, "a.txt")
        self.assertEqual(resultados[0].chunk.texto, "evidencia")

    def test_busqueda_hibrida_consulta_el_indice_lexico_persistente(self):
        class VectorFalso:
            def consultar(self, embedding, k):
                return {
                    "ids": [["doc-1#000"]], "distances": [[0.1]],
                    "documents": [["NBL 204"]],
                    "metadatas": [[{"fuente": "a.txt", "formato": "txt", "posicion": 0}],],
                }

            def todos(self):
                return {
                    "ids": ["doc-1#000"],
                    "documents": ["NBL 204"],
                    "metadatas": [{"fuente": "a.txt", "formato": "txt", "posicion": 0}],
                }

        servicio = ServicioConsultaPersistente(VectorFalso(), hibrido=True)
        with patch("rag.consulta_persistente.embed_pregunta", return_value=[1.0]):
            resultados = servicio.buscar("NBL-204")
        self.assertEqual(resultados[0].chunk.fuente, "a.txt")


class OcrTests(unittest.TestCase):
    def test_ocr_es_inyectable_y_no_se_ejecuta_sin_proveedor(self):
        self.assertEqual(
            extraer_con_ocr("archivo.pdf", lambda ruta: "texto OCR"),
            "texto OCR",
        )
        with self.assertRaises(RuntimeError):
            extraer_con_ocr("archivo.pdf")

    def test_proveedor_tesseract_informa_si_falta_el_ejecutable(self):
        provider = TesseractProvider(tesseract="ejecutable-que-no-existe")
        with self.assertRaisesRegex(RuntimeError, "Tesseract"):
            provider(Path("archivo.pdf"))


class EvaluationMetricsTests(unittest.TestCase):
    def test_metricas_de_recuperacion(self):
        resultados = ["irrelevante", "doc-b", "doc-a"]
        self.assertAlmostEqual(recall_at_k(resultados, {"doc-a", "doc-b"}, 3), 1.0)
        self.assertAlmostEqual(reciprocal_rank(resultados, {"doc-a", "doc-b"}), 0.5)
        self.assertGreater(ndcg_at_k(resultados, {"doc-a": 2.0, "doc-b": 1.0}, 3), 0.0)


class BackupTests(unittest.TestCase):
    def test_backup_y_restauracion_conservan_los_datos(self):
        with tempfile.TemporaryDirectory() as directorio:
            origen = Path(directorio) / "data"
            restaurado = Path(directorio) / "restaurado"
            origen.mkdir()
            (origen / "metadata.sqlite3").write_text("metadata", encoding="utf-8")
            backup = Path(directorio) / "backup.zip"

            crear_backup(origen, backup)
            restaurar_backup(backup, restaurado)

            self.assertEqual(
                (restaurado / "metadata.sqlite3").read_text(encoding="utf-8"),
                "metadata",
            )


class JobRetryTests(unittest.TestCase):
    def test_trabajo_fallido_puede_reiniciarse(self):
        with tempfile.TemporaryDirectory() as directorio:
            store = JobStore(Path(directorio) / "jobs.sqlite3")
            store.crear("job-1")
            store.actualizar("job-1", "failed", mensaje_error="fallo")

            self.assertTrue(store.reiniciar("job-1"))
            trabajo = store.obtener("job-1")
            self.assertEqual(trabajo["estado"], "pending")
            self.assertIsNone(trabajo["mensaje_error"])

    def test_solo_se_reintentan_trabajos_fallidos(self):
        with tempfile.TemporaryDirectory() as directorio:
            store = JobStore(Path(directorio) / "jobs.sqlite3")
            store.crear("job-1")
            self.assertFalse(store.reiniciar("job-1"))

    def test_lease_impide_dos_indexadores_simultaneos(self):
        with tempfile.TemporaryDirectory() as directorio:
            store = JobStore(Path(directorio) / "jobs.sqlite3")
            self.assertTrue(store.adquirir_lease("indexing", "worker-a"))
            self.assertFalse(store.adquirir_lease("indexing", "worker-b"))
            store.liberar_lease("indexing", "worker-a")
            self.assertTrue(store.adquirir_lease("indexing", "worker-b"))


if __name__ == "__main__":
    unittest.main()
