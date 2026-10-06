"""Modelos Pydantic de las peticiones HTTP."""

from enum import StrEnum

from pydantic import BaseModel, Field

from app.core.constantes import TOP_K_MAXIMO, TOP_K_MINIMO, TOP_K_POR_DEFECTO


class FormatoRespuesta(StrEnum):
    JSON = "json"
    TEXTO = "texto"


PREGUNTA_DE_EJEMPLO = (
    "¿Cuál es la orden del juez en el caso Morris y qué plazos fijó para el banco M&T?"
)


class ConsultaRequest(BaseModel):
    pregunta: str = Field(..., examples=[PREGUNTA_DE_EJEMPLO])
    caso: str | None = Field(None, examples=["Morris - Closed - 602074 - 21155-2012"])
    top_k: int = Field(TOP_K_POR_DEFECTO, ge=TOP_K_MINIMO, le=TOP_K_MAXIMO)


class IngestaRequest(BaseModel):
    ruta_jsonl: str | None = Field(
        None,
        description="Ruta absoluta al archivo JSONL. Por defecto usa data/pruebaocr.jsonl",
    )
