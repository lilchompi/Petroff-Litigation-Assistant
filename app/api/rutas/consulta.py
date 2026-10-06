from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.responses import PlainTextResponse

from app.api.esquemas import ConsultaRequest, FormatoRespuesta
from app.servicios.consulta import servicio_consulta

DESCRIPCION_FORMATO = "'texto' devuelve solo el dictamen en texto plano; 'json' todo el payload."

router = APIRouter(prefix="/api", tags=["consulta"])


@router.post("/consulta", response_model=None)
def consultar_agente(
    peticion: ConsultaRequest,
    formato: Annotated[FormatoRespuesta, Query(description=DESCRIPCION_FORMATO)] = (
        FormatoRespuesta.JSON
    ),
) -> dict | PlainTextResponse:
    """Consulta jurídica al Agente Claude con búsqueda semántica vectorial."""
    resultado = servicio_consulta.consultar_caso(
        pregunta=peticion.pregunta, caso=peticion.caso, top_k=peticion.top_k
    )
    if formato is FormatoRespuesta.TEXTO:
        return PlainTextResponse(content=resultado["respuesta"])
    return resultado
