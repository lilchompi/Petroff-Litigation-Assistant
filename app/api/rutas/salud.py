from fastapi import APIRouter

from app.core.config import settings
from app.core.constantes import NOMBRE_SERVICIO
from app.persistencia import almacen_documental

ESTADO_EN_LINEA = "online"

router = APIRouter(tags=["salud"])


@router.get("/health")
def estado_del_servicio() -> dict:
    """Estado del servicio, motor vectorial y configuración de modelos."""
    return {
        "status": ESTADO_EN_LINEA,
        "servicio": NOMBRE_SERVICIO,
        "motor_vectorial": almacen_documental.identificador_motor,
        "modelo_embedding": settings.EMBEDDING_MODEL_NAME,
        "dimension_embedding": settings.EMBEDDING_DIM,
        "modelo_claude": settings.CLAUDE_MODEL,
        "anthropic_api_key_configurada": bool(settings.ANTHROPIC_API_KEY),
    }
