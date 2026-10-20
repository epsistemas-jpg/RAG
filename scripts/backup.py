"""Copia y restaura el almacenamiento persistente del motor RAG."""

from __future__ import annotations

import argparse
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


def crear_backup(data_dir: str | Path, destino: str | Path) -> Path:
    origen = Path(data_dir).resolve()
    salida = Path(destino).resolve()
    if not origen.is_dir():
        raise FileNotFoundError(f"No existe el directorio de datos: {origen}")
    salida.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(salida, "w", compression=ZIP_DEFLATED) as backup:
        for archivo in origen.rglob("*"):
            if archivo.is_file() and archivo.resolve() != salida:
                backup.write(archivo, archivo.relative_to(origen).as_posix())
    return salida


def restaurar_backup(archivo_backup: str | Path, destino: str | Path) -> None:
    raiz = Path(destino).resolve()
    raiz.mkdir(parents=True, exist_ok=True)
    with ZipFile(archivo_backup) as backup:
        for miembro in backup.infolist():
            objetivo = (raiz / miembro.filename).resolve()
            if objetivo != raiz and raiz not in objetivo.parents:
                raise ValueError(f"Ruta insegura en backup: {miembro.filename}")
        backup.extractall(raiz)


def main() -> None:
    parser = argparse.ArgumentParser()
    subcomandos = parser.add_subparsers(dest="comando", required=True)
    crear = subcomandos.add_parser("crear")
    crear.add_argument("data_dir", type=Path)
    crear.add_argument("destino", type=Path)
    restaurar = subcomandos.add_parser("restaurar")
    restaurar.add_argument("backup", type=Path)
    restaurar.add_argument("destino", type=Path)
    args = parser.parse_args()
    if args.comando == "crear":
        print(crear_backup(args.data_dir, args.destino))
    else:
        restaurar_backup(args.backup, args.destino)
        print(args.destino)


if __name__ == "__main__":
    main()
