"""Revisa los JSONL por caso con las reglas que no necesitan LLM y genera un PLAN.

Solo lee SharePoint: no renombra ni mueve nada. El plan se aplica después con
`scripts.aplicar_plan`, que guarda un diario de respaldo para poder deshacerlo.

Uso:
    python -m scripts.revisar_matters                       # los .jsonl de data/
    python -m scripts.revisar_matters --desde-sharepoint    # baja los de JSONL/Casos_rafael
    python -m scripts.revisar_matters data/Claude-700171.jsonl

Deja en salida/revision/:
    plan__<fecha>.json          lo que se haría (lo lee aplicar_plan)
    informe__<fecha>.txt        el plan explicado para una persona
    hallazgos__<fecha>/         las líneas review_finding de cada caso
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

from app.core.config import RAIZ_PROYECTO, settings
from app.revision.informe_plan import informe_plan
from app.servicios.revision import descargar_jsonl, revisar_lote
from app.sharepoint import ClienteGraph

CARPETA_DATA = RAIZ_PROYECTO / "data"


def _argumentos() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("jsonl", nargs="*", type=Path, help="Por defecto, todos los de data/")
    parser.add_argument(
        "--desde-sharepoint",
        action="store_true",
        help=f"Baja los JSONL de {settings.SHAREPOINT_CARPETA_JSONL}",
    )
    return parser.parse_args()


def main() -> int:
    args = _argumentos()
    cliente = ClienteGraph()
    if args.desde_sharepoint:
        destino = settings.REVISION_DIR / "jsonl" / datetime.now().strftime("%Y%m%d-%H%M%S")
        rutas = descargar_jsonl(cliente, settings.SHAREPOINT_CARPETA_JSONL, destino)
        print(f"Descargados {len(rutas)} JSONL de {settings.SHAREPOINT_CARPETA_JSONL}")
    else:
        rutas = args.jsonl or sorted(CARPETA_DATA.glob("*.jsonl"))
    if not rutas:
        print("No hay JSONL que revisar.")
        return 1

    resultado = revisar_lote(rutas, cliente)
    incompletos = [v.ruta_jsonl.name for v in resultado.validaciones if not v.completo]
    encabezado = [
        f"Revisión de {len(rutas)} JSONL — {resultado.plan.generado}",
        "=" * 70,
        f"  JSONL completos frente a SharePoint: {len(resultado.validaciones) - len(incompletos)}"
        f" de {len(resultado.validaciones)}",
        *(f"  INCOMPLETO: {nombre}" for nombre in incompletos),
        *(f"  ERROR en {nombre}: {error}" for nombre, error in resultado.errores.items()),
        f"  Acciones en el plan: {len(resultado.plan.acciones)}",
        f"  Hallazgos: {len(resultado.plan.hallazgos)}"
        f" ({sum(h.para_llm for h in resultado.plan.hallazgos)} para el LLM)",
    ]
    texto = informe_plan(resultado.plan, encabezado)
    ruta_informe = resultado.ruta_plan.with_name(
        resultado.ruta_plan.name.replace("plan__", "informe__")
    )
    ruta_informe = ruta_informe.with_suffix(".txt")
    ruta_informe.write_text(texto + "\n", encoding="utf-8")
    print(texto)
    print(f"\nPlan:      {resultado.ruta_plan}\nInforme:   {ruta_informe}")
    print(f"Hallazgos: {resultado.ruta_hallazgos}")
    print("\nNada se ha cambiado. Para simular el plan:")
    print(f'  python -m scripts.aplicar_plan "{resultado.ruta_plan}"')
    return 0


if __name__ == "__main__":
    sys.exit(main())
