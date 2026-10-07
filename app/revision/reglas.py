"""Los parámetros de las reglas de revisión, leídos de config/reglas_revision.toml.

Así los umbrales, listas y filtros se afinan sin tocar el motor, y cada cambio queda en git.
"""

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from app.core.config import settings


@dataclass(frozen=True)
class Reglas:
    version: str = "por-defecto"
    citas_conocidas: frozenset[str] = frozenset()
    minimo_clientes_para_cita: int = 3
    minimo_documentos_para_renombrar: int = 2
    subcarpeta_fusion: str = "00_Unfiled"
    anios_en_el_futuro: int = 0
    un_digito_distinto_es_ocr: bool = False
    index_sin_carpeta_minimo_documentos: int = 1
    mismo_cliente_otro_caso_es_informativo: bool = False
    alias: tuple[frozenset[str], ...] = field(default_factory=tuple)


def cargar_reglas(ruta: Path | None = None) -> Reglas:
    ruta = ruta or settings.REGLAS_REVISION
    if not ruta.exists():
        return Reglas()
    datos = tomllib.loads(ruta.read_text(encoding="utf-8"))
    citas, renombrar = datos.get("citas", {}), datos.get("renombrar", {})
    ruido, pendientes = datos.get("ruido", {}), datos.get("pendientes", {})
    alias = datos.get("nombres", {}).get("alias", [])
    return Reglas(
        version=datos.get("version", "sin-version"),
        citas_conocidas=frozenset(citas.get("conocidas", [])),
        minimo_clientes_para_cita=citas.get("minimo_clientes", 3),
        minimo_documentos_para_renombrar=renombrar.get("minimo_documentos", 2),
        subcarpeta_fusion=datos.get("fusion", {}).get("subcarpeta", "00_Unfiled"),
        anios_en_el_futuro=ruido.get("anios_en_el_futuro", 0),
        un_digito_distinto_es_ocr=ruido.get("un_digito_distinto_es_ocr", False),
        index_sin_carpeta_minimo_documentos=pendientes.get(
            "index_sin_carpeta_minimo_documentos", 1
        ),
        mismo_cliente_otro_caso_es_informativo=pendientes.get(
            "mismo_cliente_otro_caso_es_informativo", False
        ),
        alias=tuple(frozenset(grupo) for grupo in alias),
    )
