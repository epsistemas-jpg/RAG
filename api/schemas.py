"""Esquemas públicos y estables de la API."""

from __future__ import annotations

from pydantic import AliasChoices, BaseModel, Field


class SearchRequest(BaseModel):
    # `pregunta` conserva el contrato actual; `descripcion_caso` permite que
    # el software empresarial envíe directamente el texto que escribió el
    # usuario, sin transformarlo antes de llamar al RAG.
    pregunta: str = Field(
        min_length=1,
        max_length=4000,
        validation_alias=AliasChoices("pregunta", "descripcion_caso"),
    )
    top_k: int = Field(default=4, ge=1, le=50)
    case_id: str | None = Field(default=None, max_length=200)
    jurisdiccion: str | None = Field(default=None, max_length=120)
    materia: str | None = Field(default=None, max_length=120)
    etapa: str | None = Field(default=None, max_length=120)
    confidencialidad: str | None = Field(default=None, max_length=80)


class Source(BaseModel):
    documento: str
    fragmento: str
    pagina: int | None = None
    relevancia: float | None = None
    case_id: str | None = None


class SearchResponse(BaseModel):
    resultados: list[Source]


class SimilarCasesResponse(BaseModel):
    casos: list[dict]
    probabilidad: float | None = None
    advertencias: list[str] = Field(default_factory=list)


class AskResponse(BaseModel):
    consulta_id: str
    respuesta: str | None
    fuentes: list[Source]
    advertencias: list[str] = Field(default_factory=list)


class HealthResponse(BaseModel):
    estado: str
    indice_disponible: bool


class IndexRequest(BaseModel):
    """Solicitud segura: el servidor determina el corpus configurado."""

    reiniciar: bool = False


class JobResponse(BaseModel):
    job_id: str
    estado: str


class JobStatusResponse(BaseModel):
    job_id: str
    estado: str
    total: int
    procesados: int
    mensaje_error: str | None = None


class DocumentResponse(BaseModel):
    document_id: str
    nombre: str
    extension: str
    hash_sha256: str
    tamano_bytes: int
    fecha_modificacion: float
    fecha_indexacion: str | None
    estado: str
    paginas: int | None
    fragmentos: int
    version_extractor: str
    version_embeddings: str
    mensaje_error: str | None = None
    case_id: str | None = None
