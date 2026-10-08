"""Genera el reporte para Mario de un plan ya existente, clasificado según la guía.

Los planes nuevos ya lo traen (revisar_matters y vigilar_jsonl lo escriben solos). Esto es
para los planes anteriores o para regenerarlo.

Uso:
    python -m scripts.reporte_mario salida/revision/plan__20261007-182450.json
"""

import argparse
import sys
from pathlib import Path

from app.revision.plan import Plan
from app.servicios.revision import escribir_reporte_mario


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("plan", type=Path)
    args = parser.parse_args()
    ruta = escribir_reporte_mario(Plan.cargar(args.plan), args.plan)
    print(f"Reporte para Mario: {ruta}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
