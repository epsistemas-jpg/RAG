"""Arranque de demostración en Render."""

from __future__ import annotations

import os
import subprocess
import sys


def main() -> None:
    if not os.getenv("GEMINI_API_KEY"):
        raise SystemExit("Falta GEMINI_API_KEY en las variables de Render")
    resultado = subprocess.run([sys.executable, "scripts/index_corpus.py"], check=False)
    if resultado.returncode:
        raise SystemExit(resultado.returncode)
    os.execvp(
        sys.executable,
        [sys.executable, "-m", "uvicorn", "api.runtime:app", "--host", "0.0.0.0", "--port", os.getenv("PORT", "10000")],
    )


if __name__ == "__main__":
    main()
