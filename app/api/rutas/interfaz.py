from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

RUTA_PAGINA_PRINCIPAL = Path(__file__).resolve().parents[2] / "web" / "index.html"

router = APIRouter(tags=["interfaz"])


@router.get("/", response_class=HTMLResponse)
def pagina_principal() -> str:
    """Portal web para consultar casos sin interactuar con JSON."""
    return RUTA_PAGINA_PRINCIPAL.read_text(encoding="utf-8")
