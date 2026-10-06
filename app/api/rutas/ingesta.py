from http import HTTPStatus
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.api.esquemas import IngestaRequest
from app.api.rutas.validacion import validar_o_error_http
from app.core.config import settings
from app.servicios.ingesta import ejecutar_ingesta

ESTADO_EXITO = "exito"

router = APIRouter(prefix="/api", tags=["ingesta"])


def _validacion_informativa(ruta: Path) -> dict:
    """La validación contra SharePoint como dato de la respuesta: si falla, no bloquea."""
    try:
        return validar_o_error_http(ruta, None).a_dict()
    except HTTPException as error:
        return {"error": error.detail}


@router.post("/limpiar-e-ingerir")
def limpiar_e_ingerir(peticion: IngestaRequest | None = None) -> dict:
    """Aplica las 5 reglas de limpieza y almacena los documentos vectorizados."""
    ruta_jsonl = peticion.ruta_jsonl if peticion else None
    ruta = Path(ruta_jsonl) if ruta_jsonl else settings.INPUT_JSONL
    if not ruta.exists():
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail=f"No existe {ruta}")

    respuesta: dict = {"estado": ESTADO_EXITO}
    if peticion and peticion.validar_sharepoint:
        respuesta["validacion_sharepoint"] = _validacion_informativa(ruta)
    try:
        respuesta["metricas"] = ejecutar_ingesta(ruta)
    except FileNotFoundError as error:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail=str(error)) from error
    return respuesta
