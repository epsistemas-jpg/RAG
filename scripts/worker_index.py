"""Worker durable para ejecutar trabajos pendientes de indexación.

Uso continuo:
    python scripts/worker_index.py

Una sola pasada (útil para un programador de tareas):
    python scripts/worker_index.py --once
"""

from __future__ import annotations

import argparse
import os
import time

from api.main import _ejecutar_job
from api.runtime import app


def ejecutar(una_sola: bool = False, espera: int | None = None) -> None:
    espera = espera if espera is not None else int(os.getenv("RAG_WORKER_WAIT_SECONDS", "5"))
    while True:
        trabajos = app.state.jobs.listar("pending")
        for trabajo in trabajos:
            if app.state.jobs.reclamar(trabajo["job_id"]):
                _ejecutar_job(app, trabajo["job_id"])
        if una_sola:
            return
        time.sleep(max(1, espera))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--espera", type=int, default=5)
    args = parser.parse_args()
    ejecutar(args.once, args.espera)
