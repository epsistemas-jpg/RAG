"""Compara BM25, recuperación densa e híbrida con embeddings reales."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evaluation.metrics import ndcg_at_k, recall_at_k, reciprocal_rank
from rag.carga import cargar_corpus
from rag.indice import buscar, buscar_bm25, buscar_hibrido, construir_indice


def fuentes(resultados, k: int) -> list[str]:
    salida = []
    for resultado in resultados:
        if resultado.chunk.fuente not in salida:
            salida.append(resultado.chunk.fuente)
        if len(salida) == k:
            break
    return salida


def evaluar(corpus: Path, preguntas: Path, k: int) -> dict:
    if not os.getenv("GEMINI_API_KEY"):
        raise RuntimeError("Falta GEMINI_API_KEY; esta comparación requiere embeddings reales")
    indice = construir_indice(cargar_corpus(corpus), verboso=False)
    casos = json.loads(preguntas.read_text(encoding="utf-8"))
    metodos = {"bm25": buscar_bm25, "densa": buscar, "hibrida": buscar_hibrido}
    salida = {nombre: [] for nombre in metodos}
    for caso in casos:
        relevantes = set(caso["relevantes"])
        grados = {nombre: float(valor) for nombre, valor in caso["relevantes"].items()}
        for nombre, metodo in metodos.items():
            ranked = fuentes(metodo(indice, caso["pregunta"], k=k), k)
            salida[nombre].append({
                "pregunta": caso["pregunta"], "resultados": ranked,
                "recall_at_k": recall_at_k(ranked, relevantes, k),
                "mrr": reciprocal_rank(ranked, relevantes),
                "ndcg_at_k": ndcg_at_k(ranked, grados, k),
            })
    return {
        "k": k,
        "promedios": {
            nombre: {
                metrica: sum(caso[metrica] for caso in casos_metodo) / (len(casos_metodo) or 1)
                for metrica in ("recall_at_k", "mrr", "ndcg_at_k")
            }
            for nombre, casos_metodo in salida.items()
        },
        "casos": salida,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, default=Path("corpus"))
    parser.add_argument("--preguntas", type=Path, default=Path("evaluation/preguntas.json"))
    parser.add_argument("--k", type=int, default=5)
    args = parser.parse_args()
    print(json.dumps(evaluar(args.corpus, args.preguntas, args.k), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
