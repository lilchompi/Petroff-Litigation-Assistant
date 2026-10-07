"""Deshace lo que aplicó un plan, usando su diario de respaldo.

Recorre el diario de atrás hacia adelante: devuelve cada archivo a su carpeta original y cada
carpeta a su nombre original. Si algo cambió después del plan (otra persona lo movió o lo
renombró), no lo toca y lo avisa. Las carpetas que el plan creó se dejan (vacías).

POR DEFECTO SOLO SIMULA. Para deshacer de verdad, añade --ejecutar.

Uso:
    python -m scripts.deshacer_plan salida/revision/respaldos/plan__...diario.jsonl
    python -m scripts.deshacer_plan salida/revision/respaldos/plan__...diario.jsonl --ejecutar
"""

import argparse
import sys
from pathlib import Path

from app.core.config import settings
from app.revision.ejecutor import Diario, deshacer
from app.revision.tareas_hubspot import anotar, cancelacion
from app.revision.trazabilidad import Trazabilidad
from app.sharepoint import ClienteGraph


def _carpetas_afectadas(ruta: Path) -> list[str]:
    """Una descripción por acción del diario, para anular su tarea de HubSpot."""
    por_accion: dict[str, str] = {}
    for linea in Diario.leer(ruta):
        if linea["op"] == "renombrar":
            por_accion[linea["accion"]] = (
                f"{linea['despues']['nombre']} (vuelve a ser {linea['antes']['nombre']})"
            )
        elif linea["op"] == "eliminar_carpeta":
            por_accion[linea["accion"]] = f"{linea['antes']['nombre']} (fusión deshecha)"
    return list(por_accion.values())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("diario", type=Path)
    parser.add_argument("--ejecutar", action="store_true", help="Deshacer de verdad (no simular)")
    args = parser.parse_args()

    print(
        ("DESHACIENDO" if args.ejecutar else "SIMULACIÓN (no se cambia nada)")
        + f": {args.diario.name}\n"
    )
    resultado = deshacer(
        ClienteGraph(escritura=args.ejecutar), args.diario, simular=not args.ejecutar, avisar=print
    )
    print(f"\nRevertidos: {len(resultado.hechas)}   No tocados: {len(resultado.saltadas)}")
    if resultado.error:
        print(f"PARADO POR ERROR: {resultado.error}")
    if args.ejecutar and resultado.hechas:
        anotar(settings.TAREAS_HUBSPOT, [cancelacion(c) for c in _carpetas_afectadas(args.diario)])
        print(f"Tareas de HubSpot anuladas en: {settings.TAREAS_HUBSPOT}")
        traza = Trazabilidad()
        traza.registrar_deshecho(Diario.leer(args.diario))
        traza.guardar()
    if not args.ejecutar:
        print("Para deshacer de verdad, añade --ejecutar.")
    return 1 if resultado.error else 0


if __name__ == "__main__":
    sys.exit(main())
