"""Lee de un JSONL de OCR qué archivos describe, sin cargar su texto en el resultado.

Acepta los dos formatos que salen del extractor:
- con cabecera: la primera línea trae `matter` y el resto son documentos;
- sin cabecera: cada línea trae `id` y `caso`.

Un JSONL puede traer VARIOS casos (los diarios por partes los mezclan): el caso de cada
línea sale de su `caso`, o de su `origen`, o de la cabecera.

La carpeta real del archivo está en `origen` (`/Matters/<caso>/<carpeta>`). El campo
`subfolder` no sirve para eso: muchas veces dice "(folder root)" aunque el archivo esté
en una subcarpeta.
"""

import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)

CODIFICACION = "utf-8-sig"
SUBCARPETA_RAIZ = "(folder root)"
VERDADEROS = {"true", "1", "yes", "si", "sí"}
# '/Matters/<caso>/...': la carpeta de casos y el caso.
PARTES_HASTA_EL_CASO = 2


@dataclass(frozen=True)
class ArchivoJsonl:
    linea: int
    caso: str | None
    id: str | None
    carpeta: str  # relativa a la carpeta del caso; "" es la raíz del caso
    nombre: str
    tamano_mb: float | None
    hash: str
    leido: bool
    motivo_no_leido: str

    @property
    def ruta(self) -> str:
        return f"{self.carpeta}/{self.nombre}" if self.carpeta else self.nombre


@dataclass
class InventarioJsonl:
    ruta: Path
    cabecera: dict[str, Any] | None = None
    archivos: list[ArchivoJsonl] = field(default_factory=list)
    lineas_invalidas: int = 0

    def por_caso(self) -> dict[str | None, list[ArchivoJsonl]]:
        """Los archivos agrupados por caso, en el orden en que aparecen. None = sin caso."""
        grupos: dict[str | None, list[ArchivoJsonl]] = defaultdict(list)
        for archivo in self.archivos:
            grupos[archivo.caso].append(archivo)
        return dict(grupos)


def _como_bool(valor: Any) -> bool:
    if isinstance(valor, bool):
        return valor
    return str(valor).strip().lower() in VERDADEROS


def _como_float(valor: Any) -> float | None:
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def _texto(valor: Any) -> str:
    """Cadena limpia; los 'None' que algunos JSONL guardan como texto cuentan como vacío."""
    if valor is None or str(valor).strip() == "None":
        return ""
    return str(valor).strip()


def carpeta_desde_origen(origen: str) -> str | None:
    """'/Matters/<caso>/03_Litigation/TRO' -> '03_Litigation/TRO'. None si no encaja."""
    partes = [p for p in origen.replace("\\", "/").split("/") if p]
    if len(partes) < PARTES_HASTA_EL_CASO:
        return None
    if partes[0].casefold() != settings.SHAREPOINT_CARPETA_CASOS.casefold():
        return None
    return "/".join(partes[2:])


def _caso_desde_origen(origen: str) -> str | None:
    partes = [p for p in _texto(origen).replace("\\", "/").split("/") if p]
    return partes[1] if len(partes) >= PARTES_HASTA_EL_CASO else None


def _carpeta(registro: dict[str, Any]) -> str:
    desde_origen = carpeta_desde_origen(_texto(registro.get("origen")))
    if desde_origen is not None:
        return desde_origen
    subcarpeta = _texto(registro.get("subfolder"))
    return "" if subcarpeta == SUBCARPETA_RAIZ else subcarpeta.replace("\\", "/").strip("/")


def _caso(registro: dict[str, Any], cabecera: dict[str, Any] | None) -> str | None:
    caso = _texto(registro.get("caso")) or _caso_desde_origen(registro.get("origen"))
    if not caso and cabecera:
        caso = _texto(cabecera.get("matter"))
    return caso or None


def _archivo(registro: dict[str, Any], linea: int, cabecera: dict | None) -> ArchivoJsonl:
    return ArchivoJsonl(
        linea=linea,
        caso=_caso(registro, cabecera),
        id=_texto(registro.get("id")) or None,
        carpeta=_carpeta(registro),
        nombre=_texto(registro.get("file_name")),
        tamano_mb=_como_float(registro.get("size_mb")),
        hash=_texto(registro.get("hash")),
        leido=_como_bool(registro.get("was_read")),
        motivo_no_leido=_texto(registro.get("not_read_because")),
    )


def _registros(ruta: Path) -> tuple[list[tuple[int, dict[str, Any]]], int]:
    registros, invalidas = [], 0
    with ruta.open(encoding=CODIFICACION) as archivo:
        for numero, linea in enumerate(archivo, 1):
            if not linea.strip():
                continue
            try:
                registros.append((numero, json.loads(linea)))
            except json.JSONDecodeError:
                invalidas += 1
                logger.warning("Línea %d de %s no es JSON válido; se omite.", numero, ruta)
    return registros, invalidas


def leer_inventario(ruta: Path) -> InventarioJsonl:
    """Lanza FileNotFoundError si `ruta` no existe."""
    if not ruta.exists():
        raise FileNotFoundError(f"No existe el archivo {ruta}")
    registros, invalidas = _registros(ruta)
    cabecera = None
    if registros and "matter" in registros[0][1] and "file_name" not in registros[0][1]:
        cabecera = registros.pop(0)[1]
    inventario = InventarioJsonl(ruta=ruta, cabecera=cabecera, lineas_invalidas=invalidas)
    inventario.archivos = [
        _archivo(registro, numero, cabecera)
        for numero, registro in registros
        if registro.get("file_name")
    ]
    return inventario
