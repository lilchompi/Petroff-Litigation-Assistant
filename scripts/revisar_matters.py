"""Revisa los JSONL por caso con las reglas que no necesitan LLM y genera un PLAN.

Lee los JSONL directamente de SharePoint (por defecto JSONL/Casos_rafael, Casos_gpu2 y
Casos_gpu3) EN MEMORIA: no descarga ni
guarda ninguna copia en el disco. Solo lee SharePoint: no renombra ni mueve nada. El plan se
aplica después con `scripts.aplicar_plan`, que guarda un diario de respaldo para deshacerlo.

Uso:
    python -m scripts.revisar_matters                       # las 3 carpetas de SharePoint
    python -m scripts.revisar_matters --carpeta JSONL/Casos_gpu2   # solo una carpeta
    python -m scripts.revisar_matters data/Claude-700171.jsonl   # JSONL locales concretos

Deja en salida/revision/:
    plan__<fecha>.json          lo que se haría (lo lee aplicar_plan)
    informe__<fecha>.txt        el plan explicado para una persona
    hallazgos__<fecha>/         las líneas review_finding de cada caso
    trazabilidad.csv / .log     el estado de cada carpeta de Matters/ y los eventos
    progreso.txt                el porcentaje de limpieza
"""

import argparse
import sys
from pathlib import Path

from app.core.config import settings
from app.revision.informe_plan import informe_plan
from app.revision.trazabilidad import Trazabilidad
from app.servicios.revision import ResultadoRevision, leer_jsonl_de_carpetas, revisar_lote
from app.sharepoint import ClienteGraph
from app.validacion import leer_inventario


def _argumentos() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "jsonl",
        nargs="*",
        type=Path,
        help="JSONL locales concretos (si no, se leen de SharePoint)",
    )
    parser.add_argument(
        "--carpeta",
        action="append",
        help=f"Carpeta de SharePoint con JSONL (se puede repetir). Por defecto: "
        f"{', '.join(settings.SHAREPOINT_CARPETAS_JSONL)}",
    )
    return parser.parse_args()


def _encabezado(resultado: ResultadoRevision, total: int) -> list[str]:
    incompletos = [v.ruta_jsonl.name for v in resultado.validaciones if not v.completo]
    return [
        f"Revisión de {total} JSONL — {resultado.plan.generado}",
        "=" * 70,
        f"  JSONL completos frente a SharePoint: {len(resultado.validaciones) - len(incompletos)}"
        f" de {len(resultado.validaciones)}",
        *(f"  INCOMPLETO: {nombre}" for nombre in incompletos),
        *(f"  ERROR en {nombre}: {error}" for nombre, error in resultado.errores.items()),
        f"  Acciones en el plan: {len(resultado.plan.acciones)}",
        f"  Hallazgos: {len(resultado.plan.hallazgos)}"
        f" ({sum(h.para_llm for h in resultado.plan.hallazgos)} para el LLM)",
    ]


def _trazabilidad(resultado: ResultadoRevision) -> Trazabilidad:
    carpetas = {c.id: c.titulo for c in resultado.matters.por_item.values()}
    traza = Trazabilidad()
    traza.sincronizar(carpetas)
    ids = {titulo: carpeta_id for carpeta_id, titulo in carpetas.items()}
    traza.registrar_revision(resultado.plan, resultado.cobertura, ids)
    traza.guardar()
    return traza


def main() -> int:
    args = _argumentos()
    cliente = ClienteGraph()
    if args.jsonl:
        inventarios = [leer_inventario(ruta) for ruta in args.jsonl]
    else:
        carpetas = args.carpeta or settings.SHAREPOINT_CARPETAS_JSONL
        inventarios = leer_jsonl_de_carpetas(cliente, carpetas)
        print(f"Leídos en memoria {len(inventarios)} JSONL de {', '.join(carpetas)}")
    if not inventarios:
        print("No hay JSONL que revisar.")
        return 1

    resultado = revisar_lote(inventarios, cliente)
    texto = informe_plan(resultado.plan, _encabezado(resultado, len(inventarios)))
    ruta_informe = resultado.ruta_plan.with_name(
        resultado.ruta_plan.name.replace("plan__", "informe__")
    ).with_suffix(".txt")
    ruta_informe.write_text(texto + "\n", encoding="utf-8")
    traza = _trazabilidad(resultado)

    print(texto)
    print("", *traza.resumen(), sep="\n")
    print(f"\nPlan:          {resultado.ruta_plan}\nInforme:       {ruta_informe}")
    print(f"Hallazgos:     {resultado.ruta_hallazgos}\nTrazabilidad:  {traza.ruta_csv}")
    print("\nNada se ha cambiado. Para simular el plan:")
    print(f'  python -m scripts.aplicar_plan "{resultado.ruta_plan}"')
    return 0


if __name__ == "__main__":
    sys.exit(main())
