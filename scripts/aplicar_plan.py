"""Aplica un plan de revisión en SharePoint, guardando un diario de respaldo.

POR DEFECTO SOLO SIMULA: dice qué haría y no cambia nada. Para aplicarlo de verdad hay que
añadir --ejecutar; entonces pide permiso de escritura (Sites.ReadWrite.All) al iniciar sesión.

Cada cambio queda anotado en salida/revision/respaldos/<plan>__<fecha>.diario.jsonl con su
estado de antes. Con ese diario, `scripts.deshacer_plan` lo revierte todo.

Uso:
    python -m scripts.aplicar_plan salida/revision/plan__20261006-170000.json
    python -m scripts.aplicar_plan salida/revision/plan__20261006-170000.json --ejecutar
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

from app.core.config import settings
from app.revision.ejecutor import Diario, Ejecutor
from app.revision.plan import Plan
from app.revision.tareas_hubspot import anotar, tarea_de
from app.revision.trazabilidad import Trazabilidad
from app.sharepoint import ClienteGraph


def _argumentos() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("plan", type=Path)
    parser.add_argument("--ejecutar", action="store_true", help="Aplicar de verdad (no simular)")
    return parser.parse_args()


def main() -> int:
    args = _argumentos()
    plan = Plan.cargar(args.plan)
    fecha = datetime.now().strftime("%Y%m%d-%H%M%S")
    diario = Diario(settings.REVISION_DIR / "respaldos" / f"{args.plan.stem}__{fecha}.diario.jsonl")
    modo = "EJECUTANDO" if args.ejecutar else "SIMULACIÓN (no se cambia nada)"
    print(f"{modo}: {len(plan.acciones)} acciones de {args.plan.name}\n")

    ejecutor = Ejecutor(
        ClienteGraph(escritura=args.ejecutar), diario, simular=not args.ejecutar, avisar=print
    )
    resultado = ejecutor.aplicar(plan)

    print(f"\nHechas: {len(resultado.hechas)}   Saltadas: {len(resultado.saltadas)}")
    for saltada in resultado.saltadas:
        print(f"  SALTADA {saltada}")
    if resultado.error:
        print(f"\nPARADO POR ERROR: {resultado.error}")
    if args.ejecutar and resultado.aplicadas:
        tareas = [t for t in map(tarea_de, resultado.aplicadas) if t]
        ruta_tareas = anotar(settings.TAREAS_HUBSPOT, tareas)
        traza = Trazabilidad()
        traza.registrar_aplicadas(resultado.aplicadas)
        traza.guardar()
        print("", *traza.resumen(), sep="\n")
        print(f"\nTareas para HubSpot ({len(tareas)} nuevas): {ruta_tareas}")
    if args.ejecutar and resultado.cambios:
        print(f"\nDiario de respaldo ({resultado.cambios} cambios): {diario.ruta}")
        print("Para deshacer todo lo aplicado:")
        print(f'  python -m scripts.deshacer_plan "{diario.ruta}"')
    elif not args.ejecutar:
        print("\nPara aplicarlo de verdad, añade --ejecutar.")
    return 1 if resultado.error else 0


if __name__ == "__main__":
    sys.exit(main())
