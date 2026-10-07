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

from app.revision.ejecutor import deshacer
from app.sharepoint import ClienteGraph


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
    if not args.ejecutar:
        print("Para deshacer de verdad, añade --ejecutar.")
    return 1 if resultado.error else 0


if __name__ == "__main__":
    sys.exit(main())
