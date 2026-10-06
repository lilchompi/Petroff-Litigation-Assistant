from fastapi import APIRouter

from app.persistencia import almacen_documental

router = APIRouter(prefix="/api", tags=["casos"])


@router.get("/casos")
def listar_casos() -> dict:
    """Lista los casos almacenados con su número de documentos y volumen de texto."""
    return {"casos": almacen_documental.listar_casos()}
