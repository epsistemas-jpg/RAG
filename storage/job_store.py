"""Persistencia de trabajos de indexación."""

from __future__ import annotations

import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path


class JobStore:
    def __init__(self, ruta_db: str | Path = "data/metadata.sqlite3"):
        self.ruta_db = Path(ruta_db)
        self.ruta_db.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.ruta_db) as conexion:
            conexion.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    estado TEXT NOT NULL,
                    total INTEGER NOT NULL DEFAULT 0,
                    procesados INTEGER NOT NULL DEFAULT 0,
                    creado_en TEXT NOT NULL,
                    actualizado_en TEXT NOT NULL,
                    mensaje_error TEXT
                )
                """
            )
            conexion.execute(
                """
                CREATE TABLE IF NOT EXISTS worker_leases (
                    nombre TEXT PRIMARY KEY,
                    propietario TEXT NOT NULL,
                    expira REAL NOT NULL
                )
                """
            )

    def crear(self, job_id: str, total: int = 0) -> None:
        ahora = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.ruta_db) as conexion:
            conexion.execute(
                "INSERT INTO jobs(job_id, estado, total, creado_en, actualizado_en) "
                "VALUES (?, 'pending', ?, ?, ?)",
                (job_id, total, ahora, ahora),
            )

    def actualizar(
        self,
        job_id: str,
        estado: str,
        procesados: int | None = None,
        total: int | None = None,
        mensaje_error: str | None = None,
    ) -> None:
        campos = ["estado=?", "actualizado_en=?"]
        valores: list[object] = [estado, datetime.now(timezone.utc).isoformat()]
        if procesados is not None:
            campos.append("procesados=?")
            valores.append(procesados)
        if total is not None:
            campos.append("total=?")
            valores.append(total)
        if mensaje_error is not None:
            campos.append("mensaje_error=?")
            valores.append(mensaje_error[:2000])
        valores.append(job_id)
        with sqlite3.connect(self.ruta_db) as conexion:
            conexion.execute(
                f"UPDATE jobs SET {', '.join(campos)} WHERE job_id=?", valores
            )

    def obtener(self, job_id: str) -> dict | None:
        with sqlite3.connect(self.ruta_db) as conexion:
            conexion.row_factory = sqlite3.Row
            fila = conexion.execute(
                "SELECT * FROM jobs WHERE job_id=?", (job_id,)
            ).fetchone()
        return dict(fila) if fila else None

    def listar(self, estado: str | None = None) -> list[dict]:
        consulta = "SELECT * FROM jobs"
        parametros: tuple[object, ...] = ()
        if estado:
            consulta += " WHERE estado=?"
            parametros = (estado,)
        consulta += " ORDER BY creado_en"
        with sqlite3.connect(self.ruta_db) as conexion:
            conexion.row_factory = sqlite3.Row
            filas = conexion.execute(consulta, parametros).fetchall()
        return [dict(fila) for fila in filas]

    def reclamar(self, job_id: str) -> bool:
        """Reclama atómicamente un trabajo pendiente para un worker."""
        ahora = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.ruta_db) as conexion:
            cursor = conexion.execute(
                "UPDATE jobs SET estado='processing', actualizado_en=? "
                "WHERE job_id=? AND estado='pending'",
                (ahora, job_id),
            )
        return cursor.rowcount == 1

    def adquirir_lease(self, nombre: str, propietario: str, ttl: int = 3600) -> bool:
        """Adquiere un lease entre procesos que comparten SQLite."""
        ahora = time.time()
        with sqlite3.connect(self.ruta_db, timeout=30) as conexion:
            conexion.execute("BEGIN IMMEDIATE")
            fila = conexion.execute(
                "SELECT propietario, expira FROM worker_leases WHERE nombre=?", (nombre,)
            ).fetchone()
            if fila and fila[1] > ahora and fila[0] != propietario:
                return False
            conexion.execute(
                "INSERT INTO worker_leases(nombre, propietario, expira) VALUES (?, ?, ?) "
                "ON CONFLICT(nombre) DO UPDATE SET propietario=excluded.propietario, expira=excluded.expira",
                (nombre, propietario, ahora + ttl),
            )
            return True

    def liberar_lease(self, nombre: str, propietario: str) -> None:
        with sqlite3.connect(self.ruta_db) as conexion:
            conexion.execute(
                "DELETE FROM worker_leases WHERE nombre=? AND propietario=?",
                (nombre, propietario),
            )

    def reiniciar(self, job_id: str) -> bool:
        """Deja un trabajo fallido listo para reintento."""
        ahora = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.ruta_db) as conexion:
            cursor = conexion.execute(
                "UPDATE jobs SET estado='pending', procesados=0, total=0, "
                "actualizado_en=?, mensaje_error=NULL "
                "WHERE job_id=? AND estado='failed'",
                (ahora, job_id),
            )
        return cursor.rowcount == 1
