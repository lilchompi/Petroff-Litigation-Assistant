"""Consulta jurídica: retrieval semántico + dictamen del Agente Legal Claude."""

from typing import Any

from app.core.constantes import TOP_K_POR_DEFECTO
from app.llm.cliente_claude import ClienteClaude, GeneracionDictamenError, crear_cliente_claude
from app.llm.dictamen_local import generar_dictamen_local
from app.llm.prompts import construir_mensaje_usuario
from app.persistencia import almacen_documental
from app.persistencia.almacen import AlmacenDocumental
from app.persistencia.modelos import FragmentoRecuperado
from app.rag.embeddings import GeneradorEmbeddings, generador_embeddings

RESPUESTA_SIN_DOCUMENTOS = (
    "No se encontraron documentos relevantes en la base de datos para este caso "
    "o criterio de búsqueda."
)


def _describir_fuente(numero: int, fragmento: FragmentoRecuperado) -> dict[str, Any]:
    return {
        "fuente_id": numero,
        "archivo": fragmento.file_name,
        "caso": fragmento.caso,
        "subcarpeta": fragmento.subfolder or "",
        "similitud": fragmento.similitud,
    }


class ServicioConsulta:
    def __init__(
        self,
        almacen: AlmacenDocumental,
        embeddings: GeneradorEmbeddings,
        cliente_claude: ClienteClaude | None,
    ) -> None:
        self._almacen = almacen
        self._embeddings = embeddings
        self._cliente_claude = cliente_claude

    def consultar_caso(
        self, pregunta: str, caso: str | None = None, top_k: int = TOP_K_POR_DEFECTO
    ) -> dict[str, Any]:
        fragmentos = self._almacen.busqueda_vectorial(
            self._embeddings.generar(pregunta), caso=caso, top_k=top_k
        )
        fuentes = [_describir_fuente(numero, f) for numero, f in enumerate(fragmentos, 1)]
        return {
            "pregunta": pregunta,
            "caso": caso,
            "respuesta": self._redactar_dictamen(pregunta, fragmentos),
            "total_fuentes_analizadas": len(fuentes),
            "fuentes": fuentes,
        }

    def _redactar_dictamen(self, pregunta: str, fragmentos: list[FragmentoRecuperado]) -> str:
        if not fragmentos:
            return RESPUESTA_SIN_DOCUMENTOS
        if self._cliente_claude is None:
            return generar_dictamen_local(fragmentos)
        try:
            return self._cliente_claude.generar_dictamen(
                construir_mensaje_usuario(pregunta, fragmentos)
            )
        except GeneracionDictamenError as error:
            return f"{error}\n\nContexto recuperado de forma exitosa ({len(fragmentos)} fuentes)."


servicio_consulta = ServicioConsulta(
    almacen=almacen_documental,
    embeddings=generador_embeddings,
    cliente_claude=crear_cliente_claude(),
)
