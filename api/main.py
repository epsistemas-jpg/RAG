"""Aplicación FastAPI desacoplada del arranque del índice."""

from __future__ import annotations

import os
import inspect
import time
from pathlib import Path
from secrets import compare_digest
from threading import Lock
from uuid import uuid4

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse

from api.schemas import (
    AskResponse,
    DocumentResponse,
    HealthResponse,
    IndexRequest,
    JobResponse,
    JobStatusResponse,
    SearchRequest,
    SearchResponse,
    Source,
    SimilarCasesResponse,
)
from rag.servicios import ServicioConsulta
from storage.job_store import JobStore
from api.security import RateLimiter
from api.observability import Metrics, configurar_logging, nuevo_request_id, registrar_solicitud


def _autenticar(x_api_key: str | None = Header(default=None)) -> str:
    """Autentica y devuelve el rol asociado a la clave."""
    claves = _claves_configuradas()
    if claves:
        for clave, rol in claves.items():
            if compare_digest(x_api_key or "", clave):
                return rol
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No autenticado")
    clave_configurada = os.getenv("RAG_API_KEY")
    if clave_configurada and not x_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No autenticado")
    if clave_configurada and not compare_digest(x_api_key or "", clave_configurada):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No autenticado")
    return "admin" if clave_configurada else "local"


def _claves_configuradas() -> dict[str, str]:
    """Lee RAG_API_KEYS como `clave:rol,otra-clave:consulta`."""
    resultado = {}
    for entrada in os.getenv("RAG_API_KEYS", "").split(","):
        if ":" not in entrada:
            continue
        clave, rol = entrada.split(":", 1)
        if clave.strip() and rol.strip():
            resultado[clave.strip()] = rol.strip().lower()
    return resultado


def _exigir_rol(request: Request, *roles: str) -> None:
    rol = getattr(request.state, "rag_role", "local")
    if rol == "local" and not os.getenv("RAG_API_KEY") and not _claves_configuradas():
        return
    if rol != "admin" and rol not in roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No autorizado")


def _fuente(resultado) -> Source:
    relevancia = None
    if resultado.distancia is not None:
        relevancia = 1 - resultado.distancia
    elif resultado.puntaje is not None:
        relevancia = resultado.puntaje
    return Source(
        documento=resultado.chunk.fuente,
        fragmento=resultado.chunk.texto,
        pagina=resultado.chunk.pagina,
        relevancia=relevancia,
        case_id=getattr(resultado.chunk, "case_id", None),
    )


def _filtros(request) -> dict:
    return {
        clave: valor for clave, valor in {
            "jurisdiccion": request.jurisdiccion,
            "materia": request.materia,
            "etapa": request.etapa,
            "confidencialidad": request.confidencialidad,
        }.items() if valor
    }


def create_app(
    servicio_consulta: ServicioConsulta | None = None,
    indexador=None,
    jobs: JobStore | None = None,
) -> FastAPI:
    app = FastAPI(
        title="Motor RAG",
        version="0.1.0",
        description="API independiente de recuperación y generación fundamentada.",
    )
    app.state.servicio_consulta = servicio_consulta
    app.state.indexador = indexador
    app.state.jobs = jobs
    app.state.rate_limiter = RateLimiter()
    app.state.index_lock = Lock()
    app.state.logger = configurar_logging()
    app.state.metrics = Metrics()

    @app.middleware("http")
    async def observabilidad(request: Request, call_next):
        request_id = nuevo_request_id(request)
        inicio = time.perf_counter()
        respuesta = await call_next(request)
        respuesta.headers["X-Request-ID"] = request_id
        duracion = time.perf_counter() - inicio
        registrar_solicitud(app.state.logger, request, request_id, respuesta.status_code, duracion)
        app.state.metrics.observar(respuesta.status_code, duracion)
        return respuesta

    @app.exception_handler(Exception)
    async def error_interno(request: Request, error: Exception):
        request_id = nuevo_request_id(request)
        app.state.logger.exception(
            "Error interno request_id=%s metodo=%s ruta=%s",
            request_id, request.method, request.url.path,
        )
        return JSONResponse(
            status_code=500,
            content={"error": "internal_error", "request_id": request_id},
            headers={"X-Request-ID": request_id},
        )

    def protect(request: Request, x_api_key: str | None = Header(default=None)) -> None:
        request.state.rag_role = _autenticar(x_api_key)
        app.state.rate_limiter.verificar(request)

    @app.get("/api/v1/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(
            estado="ok",
            indice_disponible=app.state.servicio_consulta is not None,
        )

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def home() -> HTMLResponse:
        archivo = Path(__file__).parent / "static" / "index.html"
        return HTMLResponse(archivo.read_text(encoding="utf-8"))

    @app.get(
        "/api/v1/metrics",
        response_class=PlainTextResponse,
        dependencies=[Depends(protect)],
    )
    def metrics() -> PlainTextResponse:
        return PlainTextResponse(
            app.state.metrics.prometheus(),
            media_type="text/plain; version=0.0.4",
        )

    @app.post(
        "/api/v1/search",
        response_model=SearchResponse,
        dependencies=[Depends(protect)],
    )
    def search(request: SearchRequest) -> SearchResponse:
        servicio = app.state.servicio_consulta
        if servicio is None:
            raise HTTPException(status_code=503, detail="Índice no disponible")
        filtros = _filtros(request)
        if request.case_id or filtros:
            resultados = servicio.buscar(
                request.pregunta, top_k=request.top_k, case_id=request.case_id,
                filtros=filtros,
            )
        else:
            resultados = servicio.buscar(request.pregunta)[: request.top_k]
        return SearchResponse(resultados=[_fuente(resultado) for resultado in resultados])

    @app.post(
        "/api/v1/similar-cases",
        response_model=SimilarCasesResponse,
        dependencies=[Depends(protect)],
    )
    def similar_cases(request: SearchRequest) -> SimilarCasesResponse:
        servicio = app.state.servicio_consulta
        if servicio is None or not hasattr(servicio, "casos_similares"):
            raise HTTPException(status_code=503, detail="Búsqueda de casos no disponible")
        filtros = _filtros(request)
        if filtros:
            casos = servicio.casos_similares(
                request.pregunta, top_k=request.top_k, filtros=filtros
            )
        else:
            casos = servicio.casos_similares(request.pregunta, top_k=request.top_k)
        return SimilarCasesResponse(
            casos=casos,
            advertencias=[
                "La similitud no es una probabilidad de ganar; faltan resultados históricos etiquetados"
            ],
        )

    @app.post(
        "/api/v1/ask",
        response_model=AskResponse,
        dependencies=[Depends(protect)],
    )
    def ask(request: SearchRequest) -> AskResponse:
        servicio = app.state.servicio_consulta
        if servicio is None:
            raise HTTPException(status_code=503, detail="Índice no disponible")
        filtros = _filtros(request)
        if request.case_id or filtros:
            resultado = servicio.responder(
                request.pregunta,
                case_id=request.case_id,
                filtros=filtros,
            )
        else:
            resultado = servicio.responder(request.pregunta)
        fuentes = [_fuente(item) for item in resultado.resultados[: request.top_k]]
        advertencias = []
        if resultado.abstencion:
            advertencias.append("Evidencia insuficiente para responder con seguridad")
        if not resultado.citas and not resultado.abstencion:
            advertencias.append("La respuesta no contiene una cita verificable")
        return AskResponse(
            consulta_id=str(uuid4()),
            respuesta=resultado.respuesta,
            fuentes=fuentes,
            advertencias=advertencias,
        )

    @app.post(
        "/api/v1/index",
        response_model=JobResponse,
        status_code=status.HTTP_202_ACCEPTED,
        dependencies=[Depends(protect)],
    )
    def index(
        _request: IndexRequest,
        background_tasks: BackgroundTasks,
        request: Request,
    ) -> JobResponse:
        _exigir_rol(request, "indexer")
        if app.state.indexador is None or app.state.jobs is None:
            raise HTTPException(status_code=503, detail="Indexador no disponible")
        job_id = str(uuid4())
        app.state.jobs.crear(job_id)
        if os.getenv("RAG_INDEX_MODE", "inline").lower() != "external":
            background_tasks.add_task(_ejecutar_job, app, job_id)
        return JobResponse(job_id=job_id, estado="pending")

    @app.get(
        "/api/v1/jobs/{job_id}",
        response_model=JobStatusResponse,
        dependencies=[Depends(protect)],
    )
    def job_status(job_id: str) -> JobStatusResponse:
        if app.state.jobs is None:
            raise HTTPException(status_code=503, detail="Gestor de trabajos no disponible")
        trabajo = app.state.jobs.obtener(job_id)
        if trabajo is None:
            raise HTTPException(status_code=404, detail="Trabajo no encontrado")
        return JobStatusResponse(**trabajo)

    @app.post(
        "/api/v1/jobs/{job_id}/retry",
        response_model=JobResponse,
        status_code=status.HTTP_202_ACCEPTED,
        dependencies=[Depends(protect)],
    )
    def retry_job(job_id: str, background_tasks: BackgroundTasks, request: Request) -> JobResponse:
        _exigir_rol(request, "indexer")
        if app.state.jobs is None or app.state.indexador is None:
            raise HTTPException(status_code=503, detail="Gestor de trabajos no disponible")
        trabajo = app.state.jobs.obtener(job_id)
        if trabajo is None:
            raise HTTPException(status_code=404, detail="Trabajo no encontrado")
        if trabajo["estado"] != "failed":
            raise HTTPException(status_code=409, detail="Solo se pueden reintentar trabajos fallidos")
        app.state.jobs.reiniciar(job_id)
        background_tasks.add_task(_ejecutar_job, app, job_id)
        return JobResponse(job_id=job_id, estado="pending")

    @app.delete(
        "/api/v1/documents/{document_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        dependencies=[Depends(protect)],
    )
    def delete_document(document_id: str, request: Request) -> None:
        _exigir_rol(request, "indexer")
        indexador = app.state.indexador
        if indexador is None:
            raise HTTPException(status_code=503, detail="Indexador no disponible")
        if indexador.metadata.obtener(document_id) is None:
            raise HTTPException(status_code=404, detail="Documento no encontrado")
        indexador.vector_store.eliminar_documento(document_id)
        indexador.metadata.eliminar(document_id)

    @app.get(
        "/api/v1/documents/{document_id}",
        response_model=DocumentResponse,
        dependencies=[Depends(protect)],
    )
    def get_document(document_id: str) -> DocumentResponse:
        indexador = app.state.indexador
        if indexador is None:
            raise HTTPException(status_code=503, detail="Indexador no disponible")
        registro = indexador.metadata.obtener(document_id)
        if registro is None:
            raise HTTPException(status_code=404, detail="Documento no encontrado")
        return DocumentResponse(
            document_id=registro.document_id,
            nombre=registro.nombre,
            extension=registro.extension,
            hash_sha256=registro.hash_sha256,
            tamano_bytes=registro.tamano_bytes,
            fecha_modificacion=registro.fecha_modificacion,
            fecha_indexacion=registro.fecha_indexacion,
            estado=registro.estado,
            paginas=registro.paginas,
            fragmentos=registro.fragmentos,
            version_extractor=registro.version_extractor,
            version_embeddings=registro.version_embeddings,
            mensaje_error=registro.mensaje_error,
            case_id=registro.case_id,
        )

    return app


def _ejecutar_job(app: FastAPI, job_id: str) -> None:
    """Punto de entrada del trabajo en segundo plano."""
    jobs = app.state.jobs
    propietario = f"pid:{__import__('os').getpid()}"
    if not jobs.adquirir_lease("indexing", propietario):
        jobs.actualizar(job_id, "failed", mensaje_error="Ya existe otro indexador activo")
        return
    with app.state.index_lock:
        try:
            jobs.actualizar(job_id, "processing")
            def progreso(procesados: int, total: int) -> None:
                jobs.actualizar(job_id, "processing", procesados=procesados, total=total)

            ejecutar = app.state.indexador.ejecutar
            if "on_progress" in inspect.signature(ejecutar).parameters:
                reporte = ejecutar(on_progress=progreso)
            else:
                reporte = ejecutar()
            procesados = reporte.nuevos + reporte.modificados + reporte.eliminados
            total = procesados + reporte.sin_cambios
            estado = "failed" if reporte.fallidos else "completed"
            jobs.actualizar(job_id, estado, procesados=procesados, total=total)
        except Exception as error:
            jobs.actualizar(job_id, "failed", mensaje_error=str(error))
        finally:
            jobs.liberar_lease("indexing", propietario)


app = create_app()
