"""Contrato opcional para OCR, sin acoplar el núcleo a un proveedor."""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import tempfile
import os
from typing import Protocol


class OcrProvider(Protocol):
    def __call__(self, ruta: Path) -> str: ...


def extraer_con_ocr(ruta: str | Path, proveedor: OcrProvider | None = None) -> str:
    if proveedor is None:
        raise RuntimeError(
            "El documento requiere OCR, pero no hay un proveedor OCR configurado"
        )
    texto = proveedor(Path(ruta))
    if not texto.strip():
        raise RuntimeError("El proveedor OCR no devolvió texto")
    return texto


class TesseractProvider:
    """OCR escalonado: renderiza páginas con Poppler y procesa Tesseract."""

    def __init__(self, idioma: str = "spa+eng", timeout_segundos: int = 120,
                 tesseract: str | None = None, pdftoppm: str = "pdftoppm"):
        self.idioma = idioma
        self.timeout_segundos = timeout_segundos
        self.tesseract = tesseract or os.getenv("RAG_TESSERACT_PATH") or _buscar_tesseract()
        self.pdftoppm = pdftoppm

    def __call__(self, ruta: Path) -> str:
        if not _ejecutable_disponible(self.tesseract):
            raise RuntimeError(
                "Tesseract no está instalado o no está en PATH; "
                "instálalo para habilitar OCR"
            )
        if ruta.suffix.lower() in {".png", ".jpg", ".jpeg", ".tif", ".tiff"}:
            resultado = subprocess.run(
                [self.tesseract, str(ruta), "stdout", "-l", self.idioma],
                check=True, timeout=self.timeout_segundos,
                capture_output=True, text=True,
            )
            return resultado.stdout.strip()
        if shutil.which(self.pdftoppm) is None:
            raise RuntimeError("pdftoppm no está instalado o no está en PATH")
        with tempfile.TemporaryDirectory() as directorio:
            prefijo = str(Path(directorio) / "pagina")
            subprocess.run(
                [self.pdftoppm, "-png", "-r", "200", str(ruta), prefijo],
                check=True, timeout=self.timeout_segundos, capture_output=True,
            )
            textos = []
            for pagina in sorted(Path(directorio).glob("pagina-*.png")):
                resultado = subprocess.run(
                    [self.tesseract, str(pagina), "stdout", "-l", self.idioma],
                    check=True, timeout=self.timeout_segundos,
                    capture_output=True, text=True,
                )
                textos.append(resultado.stdout)
            return "\n".join(textos).strip()


def _buscar_tesseract() -> str:
    """Resuelve Tesseract desde PATH o sus rutas habituales en Windows."""
    encontrado = shutil.which("tesseract")
    if encontrado:
        return encontrado
    rutas = (
        Path(os.getenv("LOCALAPPDATA", "")) / "Tesseract-OCR" / "tesseract.exe",
        Path("C:/Program Files/Tesseract-OCR/tesseract.exe"),
        Path("C:/Program Files (x86)/Tesseract-OCR/tesseract.exe"),
    )
    for ruta in rutas:
        if ruta.is_file():
            return str(ruta)
    return "tesseract"


def _ejecutable_disponible(valor: str) -> bool:
    return Path(valor).is_file() if Path(valor).parent != Path(".") else shutil.which(valor) is not None
