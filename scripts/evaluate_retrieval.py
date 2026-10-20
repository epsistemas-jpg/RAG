"""Evalúa recuperación léxica local sobre un corpus y preguntas fijas.

No llama a Gemini ni a Groq. Sirve como línea base reproducible; el mismo
conjunto de preguntas puede usarse después para comparar recuperación densa e
híbrida cuando exista un índice persistente.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rag.carga import cargar_archivo
from rag.indice import chunkear, tokenizar
from rank_bm25 import BM25Okapi
from evaluation.metrics import ndcg_at_k, recall_at_k, reciprocal_rank


def evaluar(corpus: Path, preguntas: Path, k: int = 5) -> dict:
    documentos = [
        cargar_archivo(ruta)
        for ruta in sorted(corpus.rglob("*"))
        if ruta.is_file() and ruta.suffix.lower() in {".md", ".txt", ".pdf", ".docx", ".xlsx", ".png", ".jpg", ".jpeg", ".tif", ".tiff"}
    ]
    chunks = chunkear(documentos)
    bm25 = BM25Okapi([tokenizar(chunk.texto) for chunk in chunks])
    casos = json.loads(preguntas.read_text(encoding="utf-8"))
    resultados = []
    for caso in casos:
        scores = bm25.get_scores(tokenizar(caso["pregunta"]))
        indices = sorted(range(len(scores)), key=lambda i: (-scores[i], i))
        documentos_ranked = []
        for indice in indices:
            fuente = chunks[indice].fuente
            if fuente not in documentos_ranked:
                documentos_ranked.append(fuente)
            if len(documentos_ranked) == k:
                break
        relevantes = set(caso["relevantes"])
        grados = {nombre: float(valor) for nombre, valor in caso["relevantes"].items()}
        resultados.append({
            "pregunta": caso["pregunta"],
            "resultados": documentos_ranked,
            "recall_at_k": recall_at_k(documentos_ranked, relevantes, k),
            "mrr": reciprocal_rank(documentos_ranked, relevantes),
            "ndcg_at_k": ndcg_at_k(documentos_ranked, grados, k),
        })
    total = len(resultados) or 1
    return {
        "documentos": len(documentos),
        "chunks": len(chunks),
        "k": k,
        "casos": resultados,
        "promedios": {
            "recall_at_k": sum(c["recall_at_k"] for c in resultados) / total,
            "mrr": sum(c["mrr"] for c in resultados) / total,
            "ndcg_at_k": sum(c["ndcg_at_k"] for c in resultados) / total,
        },
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
