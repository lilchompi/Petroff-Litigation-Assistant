"""Limpia los JSONL de SHAREPOINT_CARPETAS_JSONL (reglas 1-4) y deja la copia limpia en su
carpeta de Matters.

La carpeta destino sale SOLO del `sharepoint_folder_id` de la cabecera de cada JSONL (el
id no cambia aunque la carpeta se renombre). Nunca se busca por nombre. La copia limpia se
sube con el mismo nombre (`Claude-<id>.jsonl`); si ya hay uno, queda como versión nueva y
el anterior sigue en el historial de versiones.

- Los JSONL originales no se tocan.
- No se enmascaran datos (sin regla 5): el texto sigue completo, igual que el original.
- Nada se guarda en disco salvo un resumen con conteos (sin texto) en salida/limpieza/.
- Si el id ya no existe porque la carpeta se eliminó en una fusión y se recreó al deshacerla,
  la carpeta nueva se encuentra también por id: los archivos que el diario devolvió a ella
  conservan su id, y su carpeta actual es la recreada.
- Si aun así no se encuentra, o no es una carpeta de Matters, se salta y se reporta.

Uso:
    python -m scripts.limpiar_jsonl                       # simula: dice a dónde iría cada uno
    python -m scripts.limpiar_jsonl --ejecutar            # sube las copias limpias
    python -m scripts.limpiar_jsonl --ejecutar --limite 1 # prueba con uno
"""

import argparse
import csv
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from app.core.config import settings
from app.limpieza.jsonl import JsonlLimpio, limpiar_jsonl
from app.revision.ejecutor import OP_MOVER, lineas_del_diario
from app.revision.vigilancia import JsonlRemoto, listar_jsonl
from app.sharepoint import ClienteGraph, SharePointError

DESCARGAS_EN_PARALELO = 8
SUBIDO, SE_SUBIRIA = "subido", "se_subiria"
COLUMNAS = [
    "carpeta", "jsonl", "matter", "estado", "carpeta_destino", "documentos",
    "duplicados_quitados", "no_leidos", "textos_descartados", "textos_limpiados",
    "caracteres_antes", "caracteres_despues", "coverage", "partial",
]  # fmt: skip


def _archivos_sacados_por_diarios() -> dict[str, set[str]]:
    """{id de carpeta: ids de los archivos que un plan sacó de ella}, de todos los diarios."""
    sacados: dict[str, set[str]] = {}
    for diario in sorted((settings.REVISION_DIR / "respaldos").glob("*.diario.jsonl")):
        for linea in lineas_del_diario(diario):
            if linea["op"] == OP_MOVER:
                sacados.setdefault(linea["antes"]["padre"], set()).add(linea["item_id"])
    return sacados


def _carpeta_recreada(cliente: ClienteGraph, archivos: set[str]) -> str | None:
    """El id de la carpeta donde están hoy esos archivos, si están todos en la misma."""
    padres = set()
    for archivo_id in archivos:
        try:
            padres.add(cliente.obtener(archivo_id).get("parentReference", {}).get("id"))
        except SharePointError:
            continue
    return padres.pop() if len(padres) == 1 else None


def _carpeta(cliente: ClienteGraph, carpeta_id: str, sacados: dict) -> tuple[dict | None, str]:
    try:
        return cliente.obtener(carpeta_id), "ok"
    except SharePointError:
        pass
    nuevo_id = _carpeta_recreada(cliente, sacados.get(carpeta_id, set()))
    if nuevo_id is None:
        return None, "carpeta_no_existe"
    return cliente.obtener(nuevo_id), "ok_carpeta_recreada"


def _destino(
    cliente: ClienteGraph, limpio: JsonlLimpio, sacados: dict
) -> tuple[str, str, str | None]:
    """(estado, nombre de la carpeta destino, su id); el id es None si no se puede subir."""
    carpeta_id = (limpio.cabecera or {}).get("sharepoint_folder_id")
    if not carpeta_id:
        return "sin_sharepoint_folder_id", "", None
    carpeta, estado = _carpeta(cliente, carpeta_id, sacados)
    if carpeta is None:
        return estado, "", None
    padre = carpeta.get("parentReference", {}).get("path", "")
    if "folder" not in carpeta or not padre.endswith(f"/{settings.SHAREPOINT_CARPETA_CASOS}"):
        return "no_es_carpeta_de_matters", carpeta.get("name", ""), None
    return estado, carpeta["name"], carpeta["id"]


def _procesar_o_anotar(
    cliente: ClienteGraph, remoto: JsonlRemoto, ejecutar: bool, sacados: dict
) -> dict:
    """Un JSONL que falla queda anotado con su error y no detiene a los demás."""
    try:
        return _procesar(cliente, remoto, ejecutar, sacados)
    except Exception as error:
        vacia = dict.fromkeys(COLUMNAS, 0) | {"carpeta_destino": "", "matter": ""}
        return vacia | {
            "carpeta": remoto.carpeta,
            "jsonl": remoto.nombre,
            "estado": f"error: {type(error).__name__}",
            "coverage": "",
            "partial": "",
            "_motivos": {},
        }


def _procesar(cliente: ClienteGraph, remoto: JsonlRemoto, ejecutar: bool, sacados: dict) -> dict:
    limpio = limpiar_jsonl(cliente.descargar(remoto.id))
    estado, nombre_destino, carpeta_id = _destino(cliente, limpio, sacados)
    if carpeta_id:
        if ejecutar:
            cliente.subir(carpeta_id, remoto.nombre, limpio.contenido())
        sufijo = " (carpeta recreada)" if estado == "ok_carpeta_recreada" else ""
        estado = (SUBIDO if ejecutar else SE_SUBIRIA) + sufijo
    r, cabecera = limpio.resumen, limpio.cabecera or {}
    return {
        "carpeta": remoto.carpeta,
        "jsonl": remoto.nombre,
        "matter": cabecera.get("matter", ""),
        "estado": estado,
        "carpeta_destino": nombre_destino,
        "documentos": r.documentos,
        "duplicados_quitados": r.duplicados_quitados,
        "no_leidos": r.no_leidos,
        "textos_descartados": r.total_descartados,
        "textos_limpiados": r.limpiados,
        "caracteres_antes": r.caracteres_antes,
        "caracteres_despues": r.caracteres_despues,
        "coverage": cabecera.get("coverage", ""),
        "partial": cabecera.get("partial", ""),
        "_motivos": r.descartados,
    }


def _imprimir(filas: list[dict], motivos: Counter[str]) -> None:
    def total(columna: str) -> int:
        return sum(f[columna] for f in filas)

    print(f"  Documentos:            {total('documentos')}")
    print(f"  Duplicados quitados:   {total('duplicados_quitados')}")
    print(f"  No leídos por el OCR:  {total('no_leidos')}")
    print(f"  Textos limpiados:      {total('textos_limpiados')}")
    print(f"  Textos descartados:    {total('textos_descartados')} (regla 1)")
    for motivo, cantidad in motivos.most_common():
        print(f"    - {motivo}: {cantidad}")
    print("  Destino:")
    for estado, cantidad in Counter(f["estado"] for f in filas).most_common():
        print(f"    - {estado}: {cantidad}")
    for fila in filas:
        if not fila["estado"].startswith((SUBIDO, SE_SUBIRIA)):
            print(f"      {fila['estado']}: {fila['carpeta']}/{fila['jsonl']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ejecutar", action="store_true", help="Sube las copias limpias")
    parser.add_argument("--limite", type=int, help="Solo los primeros N JSONL (para probar)")
    args = parser.parse_args()

    cliente = ClienteGraph(escritura=args.ejecutar)
    remotos = listar_jsonl(cliente, settings.SHAREPOINT_CARPETAS_JSONL)[: args.limite]
    modo = "limpiando y subiendo" if args.ejecutar else "SIMULACIÓN: limpiando en memoria"
    print(f"{modo} {len(remotos)} JSONL...", flush=True)
    sacados = _archivos_sacados_por_diarios()
    with ThreadPoolExecutor(DESCARGAS_EN_PARALELO) as hilos:
        filas = list(
            hilos.map(lambda r: _procesar_o_anotar(cliente, r, args.ejecutar, sacados), remotos)
        )

    motivos: Counter[str] = Counter()
    for fila in filas:
        motivos.update(fila.pop("_motivos"))
    settings.LIMPIEZA_DIR.mkdir(parents=True, exist_ok=True)
    ruta = settings.LIMPIEZA_DIR / f"resumen__{datetime.now():%Y%m%d-%H%M%S}.csv"
    with ruta.open("w", encoding="utf-8-sig", newline="") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=COLUMNAS)
        escritor.writeheader()
        escritor.writerows(filas)

    _imprimir(filas, motivos)
    print(f"Resumen (sin texto): {ruta}")
    if not args.ejecutar:
        print(
            "Simulación: no se subió nada. Para subir: python -m scripts.limpiar_jsonl --ejecutar"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
