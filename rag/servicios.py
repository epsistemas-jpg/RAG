"""Servicios de aplicación para separar indexación, consulta y CLI."""

from __future__ import annotations

from dataclasses import dataclass

from rag.carga import Documento, cargar_corpus
from rag.configuracion import ConfiguracionRAG, validar_configuracion
from rag.generacion import citas_validas, ensamblar_prompt, generar
from rag.indice import Chunk, Indice, Resultado, buscar, construir_indice


@dataclass(frozen=True)
class RespuestaConsulta:
    """Resultado estructurado de una consulta, independiente de la interfaz."""

    pregunta: str
    respuesta: str | None
    resultados: list[Resultado]
    citas: list[str]
    similitud_mejor: float | None
    abstencion: bool


class ServicioIndexacion:
    """Construye un índice a partir de documentos ya cargados."""

    def __init__(self, configuracion: ConfiguracionRAG | None = None):
        self.configuracion = configuracion or ConfiguracionRAG()
        validar_configuracion(self.configuracion)

    def cargar_documentos(self) -> list[Documento]:
        return cargar_corpus(self.configuracion.corpus)

    def construir(self, documentos: list[Documento] | None = None) -> Indice:
        documentos = documentos if documentos is not None else self.cargar_documentos()
        return construir_indice(
            documentos,
            chunk_size=self.configuracion.chunk_size,
            chunk_overlap=self.configuracion.chunk_overlap,
        )


class ServicioConsulta:
    """Ejecuta búsqueda, abstención, generación y validación de citas."""

    def __init__(
        self,
        indice: Indice,
        configuracion: ConfiguracionRAG | None = None,
    ):
        self.indice = indice
        self.configuracion = configuracion or ConfiguracionRAG()
        validar_configuracion(self.configuracion)

    def buscar(self, pregunta: str) -> list[Resultado]:
        if not pregunta.strip():
            raise ValueError("La pregunta no puede estar vacía")
        return buscar(self.indice, pregunta, k=self.configuracion.top_k)

    def responder(self, pregunta: str) -> RespuestaConsulta:
        resultados = self.buscar(pregunta)
        similitud = 1 - resultados[0].distancia if resultados else None
        if similitud is None or similitud < self.configuracion.umbral_dominio:
            return RespuestaConsulta(
                pregunta=pregunta,
                respuesta=None,
                resultados=resultados,
                citas=[],
                similitud_mejor=similitud,
                abstencion=True,
            )

        respuesta = generar(ensamblar_prompt(resultados, pregunta))
        return RespuestaConsulta(
            pregunta=pregunta,
            respuesta=respuesta,
            resultados=resultados,
            citas=citas_validas(respuesta, resultados),
            similitud_mejor=similitud,
            abstencion=False,
        )


__all__ = [
    "ConfiguracionRAG",
    "RespuestaConsulta",
    "ServicioConsulta",
    "ServicioIndexacion",
]
