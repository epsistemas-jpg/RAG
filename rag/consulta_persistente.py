"""Consulta sobre Chroma persistente, sin reconstruir el corpus en memoria."""

from __future__ import annotations

from rag.embeddings import embed_pregunta
from rag.generacion import citas_validas, ensamblar_prompt, generar
from rag.indice import Chunk, Resultado
from rag.indice import fusionar_rrf, tokenizar
from rank_bm25 import BM25Okapi
from storage.vector_store import PersistentVectorStore


class ServicioConsultaPersistente:
    def __init__(
        self,
        vector_store: PersistentVectorStore,
        top_k: int = 4,
        umbral: float = 0.62,
        hibrido: bool = True,
    ):
        self.vector_store = vector_store
        self.top_k = top_k
        self.umbral = umbral
        self.hibrido = hibrido
        self._lexico = None
        self._chunks_lexicos = []
        self._ultima_similitud = None

    def _preparar_lexico(self) -> None:
        if self._lexico is not None:
            return
        datos = self.vector_store.todos()
        self._chunks_lexicos = []
        corpus = []
        for id_chunk, texto, metadatos in zip(
            datos.get("ids", []),
            datos.get("documents", []),
            datos.get("metadatas", []),
        ):
            self._chunks_lexicos.append(self._resultado(id_chunk, 0.0, texto, metadatos))
            corpus.append(tokenizar(texto))
        self._lexico = BM25Okapi(corpus) if corpus else None

    def buscar(self, pregunta: str, top_k: int | None = None, case_id: str | None = None, filtros: dict | None = None) -> list[Resultado]:
        limite = top_k or self.top_k
        vector = embed_pregunta(pregunta)
        where = dict(filtros or {})
        if case_id:
            where["case_id"] = case_id
        if where:
            respuesta = self.vector_store.consultar(vector, k=limite, where=where if len(where) == 1 else {"$and": [{clave: valor} for clave, valor in where.items()]})
        else:
            respuesta = self.vector_store.consultar(vector, k=limite)
        resultados = []
        for id_chunk, distancia, texto, metadatos in zip(
            respuesta["ids"][0],
            respuesta["distances"][0],
            respuesta["documents"][0],
            respuesta["metadatas"][0],
        ):
            resultados.append(
                Resultado(
                    chunk=Chunk(
                        id=id_chunk,
                        texto=texto,
                        fuente=metadatos.get("fuente", "desconocida"),
                        formato=metadatos.get("formato", ""),
                        posicion=int(metadatos.get("posicion", 0)),
                        pagina=metadatos.get("pagina"),
                        case_id=metadatos.get("case_id"),
                        metadatos=dict(metadatos),
                    ),
                    distancia=float(distancia),
                )
            )
        self._ultima_similitud = 1 - resultados[0].distancia if resultados else None
        if not self.hibrido:
            return resultados
        if not hasattr(self.vector_store, "todos"):
            return resultados
        self._preparar_lexico()
        if self._lexico is None:
            return resultados
        candidatos = self._lexico.get_scores(tokenizar(pregunta))
        mejores = sorted(range(len(candidatos)), key=lambda i: (-candidatos[i], i))
        if where:
            mejores = [
                i for i in mejores
                if all(
                    (self._chunks_lexicos[i].chunk.case_id if clave == "case_id"
                     else self._chunks_lexicos[i].chunk.metadatos.get(clave)) == valor
                    for clave, valor in where.items()
                )
            ]
        mejores = mejores[: max(10, limite)]
        lexicos = [
            Resultado(chunk=self._chunks_lexicos[i].chunk, puntaje=float(candidatos[i]))
            for i in mejores
        ]
        return fusionar_rrf([resultados, lexicos], k=limite)

    def casos_similares(self, pregunta: str, top_k: int = 10, filtros: dict | None = None) -> list[dict]:
        """Agrupa evidencia recuperada por expediente, sin inventar probabilidades."""
        agrupados: dict[str, dict] = {}
        for resultado in self.buscar(pregunta, top_k=top_k, filtros=filtros):
            case_id = resultado.chunk.case_id
            if not case_id:
                continue
            caso = agrupados.setdefault(case_id, {"case_id": case_id, "fuentes": [], "relevancia": 0.0})
            if resultado.chunk.fuente not in caso["fuentes"]:
                caso["fuentes"].append(resultado.chunk.fuente)
            caso["relevancia"] += resultado.puntaje or (1 - (resultado.distancia or 1))
        return sorted(agrupados.values(), key=lambda caso: -caso["relevancia"])[:top_k]

    @staticmethod
    def _resultado(id_chunk, distancia, texto, metadatos):
        return Resultado(
            chunk=Chunk(
                id=id_chunk,
                texto=texto,
                fuente=metadatos.get("fuente", "desconocida"),
                formato=metadatos.get("formato", ""),
                posicion=int(metadatos.get("posicion", 0)),
                pagina=metadatos.get("pagina"),
                case_id=metadatos.get("case_id"),
                metadatos=dict(metadatos),
            ),
            distancia=float(distancia),
        )

    def responder(self, pregunta: str, case_id: str | None = None, filtros: dict | None = None):
        resultados = self.buscar(pregunta, case_id=case_id, filtros=filtros)
        similitud = self._ultima_similitud
        if similitud is None or similitud < self.umbral:
            from rag.servicios import RespuestaConsulta

            return RespuestaConsulta(pregunta, None, resultados, [], similitud, True)
        respuesta = generar(ensamblar_prompt(resultados, pregunta))
        from rag.servicios import RespuestaConsulta

        return RespuestaConsulta(
            pregunta,
            respuesta,
            resultados,
            citas_validas(respuesta, resultados),
            similitud,
            False,
        )
