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


CASO_DE_EJEMPLO = "Adeyemi - Closed - 601243 - 0"


class IngestaRequest(BaseModel):
    ruta_jsonl: str | None = Field(
        None,
        description="Ruta absoluta al archivo JSONL. Por defecto usa data/pruebaocr.jsonl",
    )
    validar_sharepoint: bool = Field(
        False,
        description="Antes de ingerir, comprueba que el JSONL tenga todos los archivos del "
        "caso en SharePoint y lo incluye en la respuesta. No detiene la ingesta.",
    )


class ValidacionRequest(BaseModel):
    ruta_jsonl: str | None = Field(
        None, description="Ruta al JSONL. Por defecto, INPUT_JSONL del .env"
    )
    caso: str | None = Field(
        None,
        description="Carpeta del caso en SharePoint. Por defecto, la que indica el JSONL.",
        examples=[CASO_DE_EJEMPLO],
    )
