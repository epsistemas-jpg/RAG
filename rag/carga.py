"""Carga del corpus: del disco al texto crudo.

Regla de oro de este módulo: NO SE LIMPIA NADA.

El corpus del Instituto Nébula es sucio a propósito. Trae markdown ordenado,
exports de chat, correos reenviados, un archivo con la codificación rota y tres
PDF de calidad de extracción muy distinta. Si aquí "arreglamos" el texto, la
clase pierde justo lo que tiene que ver: que la información se degrada mucho
antes de llegar al chunking.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree

from pypdf import PdfReader

# Extensiones que sabemos leer. Cualquier otra se ignora con aviso.
EXTENSIONES = {".md", ".txt", ".pdf", ".docx", ".xlsx", ".png", ".jpg", ".jpeg", ".tif", ".tiff"}


@dataclass
class Documento:
    """Un archivo del corpus ya leído.

    texto:   el contenido tal cual salió del disco o del extractor de PDF
    fuente:  el nombre del archivo (se usa como metadato en el índice)
    formato: "md", "txt", "pdf" o "docx" (sin el punto)
    """

    texto: str
    fuente: str
    formato: str
    paginas: int | None = None
    requiere_ocr: bool = False
    paginas_texto: list[str] | None = None
    case_id: str | None = None
    metadatos: dict[str, str] | None = None


def _leer_texto_plano(ruta: Path) -> str:
    """Lee .md y .txt.

    errors="replace" es deliberado: corpus/faq_mezclado.txt trae la codificación
    rota a media página. Con errors="strict" el pipeline reventaría; con
    "replace" el archivo entra al corpus con su suciedad intacta, que es lo que
    queremos mostrar.
    """
    return ruta.read_text(encoding="utf-8", errors="replace")


def _leer_pdf(ruta: Path) -> str:
    """Lee un .pdf concatenando el texto extraído de cada página.

    Las páginas se pegan una tras otra sin meter ningún separador. Es la forma
    más común de hacerlo y también la que deja ver el problema: el encabezado y
    el pie que se repiten en cada página quedan incrustados en medio del texto,
    entre el final del contenido de una página y el principio de la siguiente.
    Hasta la manera de pegar las páginas es una decisión que afecta los chunks.

    extract_text() puede devolver None o cadena vacía en páginas sin capa de
    texto (por ejemplo un escaneo). No es un error: es información. La página
    aporta cero caracteres y así se refleja en el conteo del CP0.
    """
    return "".join(_leer_pdf_paginas(ruta))


def _leer_pdf_paginas(ruta: Path) -> list[str]:
    lector = PdfReader(str(ruta))
    return [pagina.extract_text() or "" for pagina in lector.pages]


def _leer_docx(ruta: Path) -> str:
    """Extrae párrafos y filas de tablas sin depender de Word instalado."""
    namespaces = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    with ZipFile(ruta) as archivo:
        contenido = archivo.read("word/document.xml")
    raiz = ElementTree.fromstring(contenido)
    bloques = []
    for elemento in raiz.findall(".//w:body/*", namespaces):
        nombre = elemento.tag.rsplit("}", 1)[-1]
        textos = [n.text or "" for n in elemento.findall(".//w:t", namespaces)]
        texto = "".join(textos).strip()
        if not texto:
            continue
        bloques.append(" | ".join(textos) if nombre == "tbl" else texto)
    return "\n".join(bloques)


def _leer_xlsx(ruta: Path) -> str:
    """Extrae celdas de XLSX sin depender de Excel ni de un runtime externo."""
    namespaces = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with ZipFile(ruta) as archivo:
        compartidas = []
        if "xl/sharedStrings.xml" in archivo.namelist():
            raiz = ElementTree.fromstring(archivo.read("xl/sharedStrings.xml"))
            for item in raiz.findall("a:si", namespaces):
                compartidas.append("".join(n.text or "" for n in item.findall(".//a:t", namespaces)))
        hojas = []
        for nombre in sorted(archivo.namelist()):
            if not nombre.startswith("xl/worksheets/sheet") or not nombre.endswith(".xml"):
                continue
            raiz = ElementTree.fromstring(archivo.read(nombre))
            filas = []
            for fila in raiz.findall(".//a:row", namespaces):
                valores = []
                for celda in fila.findall("a:c", namespaces):
                    valor = celda.find("a:v", namespaces)
                    texto = "" if valor is None else (valor.text or "")
                    if celda.get("t") == "s" and texto.isdigit():
                        texto = compartidas[int(texto)]
                    valores.append(texto)
                if valores:
                    filas.append(" | ".join(valores))
            if filas:
                hojas.append("\n".join(filas))
    return "\n\n".join(hojas)


def cargar_corpus(ruta: str | Path = "corpus") -> list[Documento]:
    """Recorre el directorio y despacha por extensión.

    Devuelve la lista ordenada por nombre de archivo. El orden importa: de él
    dependen los IDs de los chunks, y de los IDs depende que las demos de la
    clase salgan iguales en el ensayo y en vivo.
    """
    directorio = Path(ruta)
    if not directorio.is_dir():
        raise FileNotFoundError(
            f"No encuentro el directorio del corpus: {directorio.resolve()}\n"
            f"Corre los checkpoints desde la raíz del repositorio."
        )

    documentos: list[Documento] = []
    for archivo in sorted(directorio.iterdir()):
        if not archivo.is_file():
            continue
        extension = archivo.suffix.lower()
        if extension not in EXTENSIONES:
            print(f"  (ignorado, extensión desconocida: {archivo.name})")
            continue

        documentos.append(cargar_archivo(archivo))

    if not documentos:
        raise FileNotFoundError(
            f"El directorio {directorio.resolve()} no tiene formatos admitidos."
        )

    return documentos


def cargar_archivo(ruta: str | Path) -> Documento:
    """Extrae un único archivo para permitir indexación incremental."""
    archivo = Path(ruta)
    if not archivo.is_file():
        raise FileNotFoundError(f"No encuentro el archivo: {archivo}")
    extension = archivo.suffix.lower()
    if extension not in EXTENSIONES:
        raise ValueError(f"Extensión no admitida: {extension or '(sin extensión)'}")
    paginas = None
    requiere_ocr = False
    paginas_texto = None
    if extension == ".pdf":
        paginas_texto = _leer_pdf_paginas(archivo)
        texto = "".join(paginas_texto)
        paginas = len(paginas_texto)
        requiere_ocr = not texto.strip()
    elif extension == ".docx":
        texto = _leer_docx(archivo)
    elif extension == ".xlsx":
        texto = _leer_xlsx(archivo)
    elif extension in {".png", ".jpg", ".jpeg", ".tif", ".tiff"}:
        texto = ""
        paginas = 1
        requiere_ocr = True
    else:
        texto = _leer_texto_plano(archivo)
    return Documento(
        texto=texto,
        fuente=archivo.name,
        formato=extension.lstrip("."),
        paginas=paginas,
        requiere_ocr=requiere_ocr,
        paginas_texto=paginas_texto,
    )
