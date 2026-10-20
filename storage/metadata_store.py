"""Registro persistente de documentos y trabajos mediante SQLite."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class DocumentoRegistro:
    document_id: str
    ruta: str
    nombre: str
    extension: str
    hash_sha256: str
    tamano_bytes: int
    fecha_modificacion: float
    fecha_indexacion: str | None = None
    estado: str = "pending"
    paginas: int | None = None
    fragmentos: int = 0
    version_extractor: str = "1"
    version_embeddings: str = ""
    mensaje_error: str | None = None
    case_id: str | None = None


class MetadataStore:
    """Almacena el estado documental sin duplicar el texto completo."""

    def __init__(self, ruta_db: str | Path = "data/metadata.sqlite3"):
        self.ruta_db = Path(ruta_db)
        self.ruta_db.parent.mkdir(parents=True, exist_ok=True)
        self._inicializar()

    def _conexion(self) -> sqlite3.Connection:
        conexion = sqlite3.connect(self.ruta_db)
        conexion.row_factory = sqlite3.Row
        return conexion

    def _inicializar(self) -> None:
        with self._conexion() as conexion:
            conexion.execute(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    document_id TEXT PRIMARY KEY,
                    ruta TEXT NOT NULL,
                    nombre TEXT NOT NULL,
                    extension TEXT NOT NULL,
                    hash_sha256 TEXT NOT NULL,
                    tamano_bytes INTEGER NOT NULL,
                    fecha_modificacion REAL NOT NULL,
                    fecha_indexacion TEXT,
                    estado TEXT NOT NULL,
                    paginas INTEGER,
                    fragmentos INTEGER NOT NULL DEFAULT 0,
                    version_extractor TEXT NOT NULL,
                    version_embeddings TEXT NOT NULL,
                    mensaje_error TEXT
                )
                """
            )
            conexion.execute(
                "CREATE INDEX IF NOT EXISTS idx_documents_hash "
                "ON documents(hash_sha256)"
            )
            columnas = {fila[1] for fila in conexion.execute("PRAGMA table_info(documents)")}
            if "case_id" not in columnas:
                conexion.execute("ALTER TABLE documents ADD COLUMN case_id TEXT")

    def upsert(self, registro: DocumentoRegistro) -> None:
        with self._conexion() as conexion:
            conexion.execute(
                """
                INSERT INTO documents (
                    document_id, ruta, nombre, extension, hash_sha256,
                    tamano_bytes, fecha_modificacion, fecha_indexacion, estado,
                    paginas, fragmentos, version_extractor, version_embeddings,
                    mensaje_error, case_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(document_id) DO UPDATE SET
                    ruta=excluded.ruta,
                    nombre=excluded.nombre,
                    extension=excluded.extension,
                    hash_sha256=excluded.hash_sha256,
                    tamano_bytes=excluded.tamano_bytes,
                    fecha_modificacion=excluded.fecha_modificacion,
                    fecha_indexacion=excluded.fecha_indexacion,
                    estado=excluded.estado,
                    paginas=excluded.paginas,
                    fragmentos=excluded.fragmentos,
                    version_extractor=excluded.version_extractor,
                    version_embeddings=excluded.version_embeddings,
                    mensaje_error=excluded.mensaje_error,
                    case_id=excluded.case_id
                """,
                (
                    registro.document_id,
                    registro.ruta,
                    registro.nombre,
                    registro.extension,
                    registro.hash_sha256,
                    registro.tamano_bytes,
                    registro.fecha_modificacion,
                    registro.fecha_indexacion,
                    registro.estado,
                    registro.paginas,
                    registro.fragmentos,
                    registro.version_extractor,
                    registro.version_embeddings,
                    registro.mensaje_error,
                    registro.case_id,
                ),
            )

    def obtener(self, document_id: str) -> DocumentoRegistro | None:
        with self._conexion() as conexion:
            fila = conexion.execute(
                "SELECT * FROM documents WHERE document_id = ?", (document_id,)
            ).fetchone()
        return self._desde_fila(fila) if fila else None

    def por_ruta(self, ruta: str) -> DocumentoRegistro | None:
        with self._conexion() as conexion:
            fila = conexion.execute(
                "SELECT * FROM documents WHERE ruta = ?", (ruta,)
            ).fetchone()
        return self._desde_fila(fila) if fila else None

    def listar(self) -> list[DocumentoRegistro]:
        with self._conexion() as conexion:
            filas = conexion.execute(
                "SELECT * FROM documents ORDER BY document_id"
            ).fetchall()
        return [self._desde_fila(fila) for fila in filas]

    def marcar_completado(
        self,
        document_id: str,
        fragmentos: int,
        paginas: int | None = None,
    ) -> None:
        with self._conexion() as conexion:
            conexion.execute(
                """
                UPDATE documents
                SET estado='completed', fragmentos=?, paginas=?,
                    fecha_indexacion=?, mensaje_error=NULL
                WHERE document_id=?
                """,
                (
                    fragmentos,
                    paginas,
                    datetime.now(timezone.utc).isoformat(),
                    document_id,
                ),
            )

    def marcar_error(self, document_id: str, mensaje: str) -> None:
        with self._conexion() as conexion:
            conexion.execute(
                "UPDATE documents SET estado='failed', mensaje_error=? "
                "WHERE document_id=?",
                (mensaje[:2000], document_id),
            )

    def eliminar(self, document_id: str) -> None:
        with self._conexion() as conexion:
            conexion.execute("DELETE FROM documents WHERE document_id=?", (document_id,))

    def vaciar(self) -> None:
        """Elimina el registro documental para una reconstrucción explícita."""
        with self._conexion() as conexion:
            conexion.execute("DELETE FROM documents")

    @staticmethod
    def _desde_fila(fila: sqlite3.Row) -> DocumentoRegistro:
        return DocumentoRegistro(**dict(fila))
