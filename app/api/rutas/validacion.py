from http import HTTPStatus
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse

from app.api.esquemas import FormatoRespuesta, ValidacionRequest
from app.core.config import settings
from app.servicios.validacion import (
    CasoDesconocidoError,
    ValidacionJsonl,
    validar_jsonl_contra_sharepoint,
)
from app.sharepoint import CasoNoEncontradoError, SharePointError, SharePointNoConfiguradoError

DESCRIPCION_FORMATO = "'texto' devuelve el informe legible por carpetas; 'json' el detalle."

router = APIRouter(prefix="/api", tags=["validacion"])


def validar_o_error_http(ruta: Path, caso: str | None) -> ValidacionJsonl:
    """Ejecuta la validación traduciendo cada fallo a su código HTTP."""
    try:
        return validar_jsonl_contra_sharepoint(ruta, caso)
    except (FileNotFoundError, CasoNoEncontradoError) as error:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail=str(error)) from error
    except CasoDesconocidoError as error:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=str(error)) from error
    except SharePointNoConfiguradoError as error:
        raise HTTPException(
            status_code=HTTPStatus.SERVICE_UNAVAILABLE, detail=str(error)
        ) from error
    except SharePointError as error:
        raise HTTPException(status_code=HTTPStatus.BAD_GATEWAY, detail=str(error)) from error


@router.post("/validar-sharepoint", response_model=None)
def validar_sharepoint(
    peticion: ValidacionRequest | None = None,
    formato: Annotated[FormatoRespuesta, Query(description=DESCRIPCION_FORMATO)] = (
        FormatoRespuesta.JSON
    ),
) -> dict | PlainTextResponse:
    """Comprueba por `id` que el JSONL tenga todos los archivos de sus casos en SharePoint.

    Si el JSONL trae varios casos, valida cada uno contra su carpeta de Matters/. Dice qué
    archivos faltan, por caso y por carpeta, y cuáles sobran, no traen id, se movieron,
    cambiaron de tamaño o quedaron sin leer. El informe queda guardado en
    salida/validaciones/.
    """
    ruta = Path(peticion.ruta_jsonl) if peticion and peticion.ruta_jsonl else settings.INPUT_JSONL
    validacion = validar_o_error_http(ruta, peticion.caso if peticion else None)
    if formato is FormatoRespuesta.TEXTO:
        return PlainTextResponse(content=validacion.informe_txt.read_text(encoding="utf-8"))
    return validacion.a_dict()
