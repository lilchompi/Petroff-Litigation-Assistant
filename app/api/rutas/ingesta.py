from http import HTTPStatus
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.api.esquemas import IngestaRequest
from app.core.config import settings
from app.servicios.ingesta import ejecutar_ingesta

ESTADO_EXITO = "exito"

router = APIRouter(prefix="/api", tags=["ingesta"])


@router.post("/limpiar-e-ingerir")
def limpiar_e_ingerir(peticion: IngestaRequest | None = None) -> dict:
    """Aplica las 5 reglas de limpieza y almacena los documentos vectorizados."""
    ruta_jsonl = peticion.ruta_jsonl if peticion else None
    ruta = Path(ruta_jsonl) if ruta_jsonl else settings.INPUT_JSONL
    try:
        metricas = ejecutar_ingesta(ruta)
    except FileNotFoundError as error:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail=str(error)) from error
    return {"estado": ESTADO_EXITO, "metricas": metricas}
