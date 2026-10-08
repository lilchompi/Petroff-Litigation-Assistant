"""Deshace lo que aplicó un plan, usando su diario de respaldo.

Recorre el diario de atrás hacia adelante: devuelve cada archivo a su carpeta original, cada
carpeta a su nombre original y vuelve a crear las carpetas que una fusión eliminó. Si algo
cambió después del plan (otra persona lo movió o lo renombró), no lo toca y lo avisa.

POR DEFECTO SOLO SIMULA. Para deshacer de verdad, añade --ejecutar.

Uso:
    python -m scripts.deshacer_plan salida/revision/respaldos/plan__...diario.jsonl
    python -m scripts.deshacer_plan salida/revision/respaldos/plan__...diario.jsonl --ejecutar
    python -m scripts.deshacer_plan <diario> --solo-fusiones --ejecutar   # deja los renombres
"""

import argparse
import sys
from pathlib import Path

from app.core.config import settings
from app.revision.ejecutor import deshacer, lineas_del_diario
from app.revision.tareas_hubspot import anotar, cancelacion
from app.revision.trazabilidad import Trazabilidad
from app.sharepoint import ClienteGraph


def _carpetas_afectadas(lineas: list[dict]) -> list[str]:
    """Una descripción por acción revertida, para anular su tarea de HubSpot."""
    por_accion: dict[str, str] = {}
    for linea in lineas:
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
    parser.add_argument(
        "--solo-fusiones", action="store_true", help="Revertir solo las fusiones (no los renombres)"
    )
    args = parser.parse_args()
    tipos = {"fusionar"} if args.solo_fusiones else None

    modo = "DESHACIENDO" if args.ejecutar else "SIMULACIÓN (no se cambia nada)"
    alcance = " (solo fusiones)" if tipos else ""
    print(f"{modo}{alcance}: {args.diario.name}\n")
    resultado = deshacer(
        ClienteGraph(escritura=args.ejecutar),
        args.diario,
        simular=not args.ejecutar,
        avisar=print,
        tipos=tipos,
    )
    print(f"\nRevertidos: {len(resultado.hechas)}   No tocados: {len(resultado.saltadas)}")
    if resultado.error:
        print(f"PARADO POR ERROR: {resultado.error}")
    if args.ejecutar and resultado.hechas:
        lineas = lineas_del_diario(args.diario, tipos)
        ruta = anotar(
            settings.TAREAS_HUBSPOT, [cancelacion(c) for c in _carpetas_afectadas(lineas)]
        )
        print(f"Tareas de HubSpot anuladas en: {ruta}")
        traza = Trazabilidad()
        traza.registrar_deshecho(lineas)
        traza.guardar()
    if not args.ejecutar:
        print("Para deshacer de verdad, añade --ejecutar.")
    return 1 if resultado.error else 0


if __name__ == "__main__":
    sys.exit(main())
