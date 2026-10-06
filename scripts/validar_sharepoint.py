"""Comprueba por `id` que cada JSONL tenga todos los archivos de sus casos en SharePoint.

Sin argumentos valida todos los .jsonl de data/. Solo lee SharePoint, no cambia nada.
Si un JSONL trae varios casos, valida cada uno contra su carpeta de Matters/.
La primera vez abre el navegador para iniciar sesión con la cuenta de @petroffamshen.com.
Cada informe queda guardado en salida/validaciones/ (.txt legible y .json).

Uso:
    python -m scripts.validar_sharepoint
    python -m scripts.validar_sharepoint data/Allard_500291.jsonl
    python -m scripts.validar_sharepoint archivo.jsonl --caso "Adeyemi - Closed - 601243 - 0"

Termina con código 1 si a algún JSONL le faltan archivos o tiene líneas sin id.
"""

import argparse
import sys
from pathlib import Path

from app.core.config import RAIZ_PROYECTO
from app.servicios.validacion import CasoDesconocidoError, validar_jsonl_contra_sharepoint
from app.sharepoint import ClienteGraph, SharePointError

CARPETA_DATA = RAIZ_PROYECTO / "data"


def _argumentos() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("jsonl", nargs="*", type=Path, help="Por defecto, todos los de data/")
    parser.add_argument(
        "--caso", help="Compara todo el JSONL contra esta carpeta, si no indica su caso"
    )
    return parser.parse_args()


def main() -> int:
    args = _argumentos()
    rutas = args.jsonl or sorted(CARPETA_DATA.glob("*.jsonl"))
    if not rutas:
        print(f"No hay archivos .jsonl en {CARPETA_DATA}")
        return 1

    cliente = ClienteGraph()
    incompletos = 0
    for ruta in rutas:
        print(f"\n### {ruta.name}")
        try:
            validacion = validar_jsonl_contra_sharepoint(ruta, args.caso, cliente)
        except (FileNotFoundError, CasoDesconocidoError, SharePointError) as error:
            print(f"  ERROR: {error}")
            incompletos += 1
            continue
        print(validacion.informe())
        print("\n  Informe guardado en:")
        print(f"    {validacion.informe_txt}\n    {validacion.informe_json}")
        incompletos += not validacion.completo
    return 1 if incompletos else 0


if __name__ == "__main__":
    sys.exit(main())
