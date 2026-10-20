"""Métricas estándar para evaluar resultados recuperados."""

from __future__ import annotations

import math


def recall_at_k(resultados: list[str], relevantes: set[str], k: int) -> float:
    if not relevantes:
        return 0.0
    encontrados = set(resultados[:k]) & relevantes
    return len(encontrados) / len(relevantes)


def reciprocal_rank(resultados: list[str], relevantes: set[str]) -> float:
    for posicion, resultado in enumerate(resultados, start=1):
        if resultado in relevantes:
            return 1.0 / posicion
    return 0.0


def ndcg_at_k(resultados: list[str], relevantes: dict[str, float], k: int) -> float:
    def dcg(ids: list[str]) -> float:
        return sum(
            (2 ** relevantes.get(resultado, 0.0) - 1) / math.log2(posicion + 2)
            for posicion, resultado in enumerate(ids)
        )

    observado = dcg(resultados[:k])
    ideal = dcg(sorted(relevantes, key=relevantes.get, reverse=True)[:k])
    return observado / ideal if ideal else 0.0
