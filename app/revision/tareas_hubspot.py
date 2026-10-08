"""Las tareas que deja cada cambio aplicado en SharePoint para quien maneja HubSpot.

La guía pide cambiar carpeta y Matter a la vez ("los dos, no uno"). Como el sistema solo
cambia SharePoint, cada acción aplicada añade una fila a un CSV que se abre en Excel, con lo
que hay que cambiar en HubSpot, dónde y por qué. Si la acción se deshace, se añade otra fila
que dice que esa tarea ya no hay que hacerla.
"""

import csv
from pathlib import Path

from app.revision.nombres import leer_nombre
from app.revision.plan import FUSIONAR, RENOMBRAR, Accion, ahora

# utf-8-sig: Excel en Windows reconoce así los acentos al abrir el CSV.
CODIFICACION = "utf-8-sig"
COLUMNAS = [
    "fecha",
    "tarea",
    "id_interno",
    "carpeta_en_sharepoint",
    "campo_hubspot",
    "valor_nuevo",
    "que_hacer",
    "por_que",
    "estado",
    "hecho_por",
]


def _renombre(accion: Accion) -> dict[str, str]:
    d = accion.datos
    nombre = leer_nombre(d["nombre_nuevo"])
    return {
        "tarea": "Actualizar index",
        "id_interno": nombre.id_interno or "",
        "carpeta_en_sharepoint": d["nombre_nuevo"],
        "campo_hubspot": "index_number",
        "valor_nuevo": nombre.index or "",
        "que_hacer": (
            f"Buscar el Deal del ID interno {nombre.id_interno} y poner {nombre.index} en "
            f"index_number. Antes la carpeta se llamaba '{d['nombre_actual']}'."
        ),
        "por_que": accion.motivo,
    }


def _fusion(accion: Accion) -> dict[str, str]:
    d = accion.datos
    origen, destino = leer_nombre(d["origen_nombre"]), leer_nombre(d["destino_nombre"])
    return {
        "tarea": "Dejar un solo Matter",
        "id_interno": f"{origen.id_interno} -> {destino.id_interno}",
        "carpeta_en_sharepoint": d["destino_nombre"],
        "campo_hubspot": "(Deal completo)",
        "valor_nuevo": f"Conservar el Matter del ID {destino.id_interno}",
        "que_hacer": (
            f"La carpeta '{d['origen_nombre']}' (ID {origen.id_interno}) se fusionó dentro de "
            f"'{d['destino_nombre']}' (ID {destino.id_interno}) y ya no existe. Archivar o "
            f"fusionar en HubSpot el Matter del ID {origen.id_interno} con el del "
            f"ID {destino.id_interno}."
        ),
        "por_que": f"{accion.regla}: {accion.motivo}",
    }


def tarea_de(accion: Accion) -> dict[str, str] | None:
    if accion.tipo == RENOMBRAR:
        fila = _renombre(accion)
    elif accion.tipo == FUSIONAR:
        fila = _fusion(accion)
    else:
        return None
    return {"fecha": ahora(), **fila, "estado": "pendiente", "hecho_por": ""}


def cancelacion(descripcion: str) -> dict[str, str]:
    """La fila que anula una tarea cuando su cambio en SharePoint se deshizo."""
    return {
        "fecha": ahora(),
        "tarea": "NO HACER (se deshizo)",
        "id_interno": "",
        "carpeta_en_sharepoint": descripcion,
        "campo_hubspot": "",
        "valor_nuevo": "",
        "que_hacer": "Este cambio se deshizo en SharePoint: no aplicar su tarea en HubSpot.",
        "por_que": "deshacer_plan",
        "estado": "cancelada",
        "hecho_por": "",
    }


def _escribir(ruta: Path, filas: list[dict[str, str]]) -> None:
    nuevo = not ruta.exists()
    with ruta.open("a", encoding=CODIFICACION, newline="") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=COLUMNAS)
        if nuevo:
            escritor.writeheader()
        escritor.writerows(filas)


def anotar(ruta: Path, filas: list[dict[str, str]]) -> Path | None:
    """Añade filas al CSV de tareas (lo crea con encabezado si no existe).

    Si el CSV está abierto en Excel (Windows lo bloquea), las filas van a un archivo aparte,
    <nombre>__pendiente_<fecha>.csv, para no perderlas. Devuelve la ruta donde se escribió.
    """
    if not filas:
        return None
    ruta.parent.mkdir(parents=True, exist_ok=True)
    try:
        _escribir(ruta, filas)
    except PermissionError:
        ruta = ruta.with_name(f"{ruta.stem}__pendiente_{ahora().replace(':', '')}.csv")
        _escribir(ruta, filas)
    return ruta
