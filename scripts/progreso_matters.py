"""Muestra cuánto va de la limpieza de Matters/: porcentajes y qué carpetas faltan.

No llama a SharePoint: lee salida/revision/trazabilidad.csv, que se actualiza solo al
revisar, aplicar y deshacer.

Uso:
    python -m scripts.progreso_matters
    python -m scripts.progreso_matters --estado "pendiente: aplicar plan"
    python -m scripts.progreso_matters --estado limpia
"""

import argparse
import sys

from app.revision.trazabilidad import ORDEN_ESTADOS, Trazabilidad


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--estado", choices=ORDEN_ESTADOS, help="Listar las carpetas en ese estado")
    args = parser.parse_args()

    traza = Trazabilidad()
    if not traza.filas:
        print("Todavía no hay trazabilidad: corre primero  python -m scripts.revisar_matters")
        return 1
    print("\n".join(traza.resumen()))
    if args.estado:
        carpetas = sorted(f["carpeta"] for f in traza.filas.values() if f["estado"] == args.estado)
        print(f"\n{args.estado} ({len(carpetas)}):")
        print("\n".join(f"  - {c}" for c in carpetas))
    print(f"\nDetalle por carpeta (Excel): {traza.ruta_csv}\nEventos: {traza.ruta_log}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
