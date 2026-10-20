"""Descubrimiento y planificación incremental de documentos."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from storage.metadata_store import DocumentoRegistro, MetadataStore


EXTENSIONES_ADMITIDAS = {".md", ".txt", ".pdf", ".docx", ".xlsx", ".png", ".jpg", ".jpeg", ".tif", ".tiff"}
VERSION_EXTRACTOR = "1"


@dataclass(frozen=True)
class DocumentoDetectado:
    document_id: str
    ruta: Path
    nombre: str
    extension: str
    hash_sha256: str
    tamano_bytes: int
    fecha_modificacion: float
    case_id: str | None = None
    metadatos_caso: dict[str, str] | None = None


@dataclass(frozen=True)
class PlanIndexacion:
    nuevos: list[DocumentoDetectado]
    modificados: list[DocumentoDetectado]
    sin_cambios: list[DocumentoDetectado]
    eliminados: list[DocumentoRegistro]


class DocumentService:
    """Compara el sistema de archivos con el registro persistente."""

    def __init__(
        self,
        raiz: str | Path,
        metadata: MetadataStore,
        extensiones: set[str] | None = None,
    ):
        self.raiz = Path(raiz).resolve()
        self.metadata = metadata
        self.extensiones = extensiones or EXTENSIONES_ADMITIDAS

    def descubrir(self) -> list[DocumentoDetectado]:
        if not self.raiz.is_dir():
            raise FileNotFoundError(f"No existe el corpus: {self.raiz}")

        encontrados = []
        for ruta in sorted(self.raiz.rglob("*")):
            if not ruta.is_file() or ruta.suffix.lower() not in self.extensiones:
                continue
            encontrados.append(self._detectar(ruta))
        return encontrados

    def planificar(self) -> PlanIndexacion:
        actuales = self.descubrir()
        registrados = {registro.document_id: registro for registro in self.metadata.listar()}
        nuevos = []
        modificados = []
        sin_cambios = []

        for documento in actuales:
            anterior = registrados.pop(documento.document_id, None)
            if anterior is None:
                nuevos.append(documento)
            elif self._requiere_procesamiento(anterior, documento):
                modificados.append(documento)
            else:
                sin_cambios.append(documento)

        return PlanIndexacion(
            nuevos=nuevos,
            modificados=modificados,
            sin_cambios=sin_cambios,
            eliminados=list(registrados.values()),
        )

    def registrar_pendiente(self, documento: DocumentoDetectado, version_embeddings: str) -> None:
        self.metadata.upsert(
            DocumentoRegistro(
                document_id=documento.document_id,
                ruta=str(documento.ruta),
                nombre=documento.nombre,
                extension=documento.extension,
                hash_sha256=documento.hash_sha256,
                tamano_bytes=documento.tamano_bytes,
                fecha_modificacion=documento.fecha_modificacion,
                estado="pending",
                version_extractor=VERSION_EXTRACTOR,
                version_embeddings=version_embeddings,
                case_id=documento.case_id,
            )
        )

    def _detectar(self, ruta: Path) -> DocumentoDetectado:
        ruta_relativa = ruta.relative_to(self.raiz).as_posix()
        partes = ruta.relative_to(self.raiz).parts
        case_id = partes[0] if len(partes) > 1 else None
        metadatos_caso = self._leer_metadatos_caso(case_id)
        return DocumentoDetectado(
            document_id=hashlib.sha256(ruta_relativa.encode("utf-8")).hexdigest(),
            ruta=ruta,
            nombre=ruta.name,
            extension=ruta.suffix.lower(),
            hash_sha256=self._hash_archivo(ruta),
            tamano_bytes=ruta.stat().st_size,
            fecha_modificacion=ruta.stat().st_mtime,
            case_id=case_id,
            metadatos_caso=metadatos_caso,
        )

    def _leer_metadatos_caso(self, case_id: str | None) -> dict[str, str] | None:
        if not case_id:
            return None
        for nombre in ("case.json", "_case.json"):
            ruta = self.raiz / case_id / nombre
            if not ruta.is_file():
                continue
            try:
                datos = json.loads(ruta.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
                raise ValueError(f"Metadatos inválidos en {ruta}: {error}") from error
            permitidos = {"jurisdiccion", "materia", "etapa", "confidencialidad", "resultado"}
            return {clave: str(valor) for clave, valor in datos.items() if clave in permitidos}
        return None

    @staticmethod
    def _hash_archivo(ruta: Path) -> str:
        digest = hashlib.sha256()
        with ruta.open("rb") as archivo:
            for bloque in iter(lambda: archivo.read(1024 * 1024), b""):
                digest.update(bloque)
        return digest.hexdigest()

    @staticmethod
    def _requiere_procesamiento(
        anterior: DocumentoRegistro,
        actual: DocumentoDetectado,
    ) -> bool:
        return (
            anterior.hash_sha256 != actual.hash_sha256
            or anterior.tamano_bytes != actual.tamano_bytes
            or anterior.fecha_modificacion != actual.fecha_modificacion
            or anterior.estado != "completed"
            or anterior.version_extractor != VERSION_EXTRACTOR
        )
