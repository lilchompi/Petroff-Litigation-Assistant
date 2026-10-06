"""Validación: ¿el JSONL que llegó tiene todos los archivos de sus casos en SharePoint?

Un JSONL puede traer uno o varios casos. Cada caso se compara por `id` con su carpeta en
Matters/, y el informe de todos queda guardado junto en VALIDACIONES_DIR.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from app.core.config import settings
from app.sharepoint import CasoNoEncontradoError, ClienteGraph
from app.validacion import (
    ArchivoJsonl,
    ResultadoValidacion,
    comparar,
    informe_varios_casos,
    leer_inventario,
)

FORMATO_FECHA = "%Y%m%d-%H%M%S"
CODIFICACION = "utf-8"


class CasoDesconocidoError(ValueError):
    """El JSONL no dice de qué caso es ninguna línea y no se indicó uno."""


@dataclass
class ValidacionJsonl:
    ruta_jsonl: Path
    resultados: list[ResultadoValidacion] = field(default_factory=list)
    # Casos del JSONL cuya carpeta no está en SharePoint: {caso: motivo}.
    errores: dict[str, str] = field(default_factory=dict)
    lineas_sin_caso: int = 0
    informe_txt: Path | None = None
    informe_json: Path | None = None

    @property
    def completo(self) -> bool:
        return not self.errores and all(r.completo for r in self.resultados)

    def informe(self) -> str:
        return informe_varios_casos(self.resultados, self.errores, self.lineas_sin_caso)

    def a_dict(self) -> dict:
        return {
            "jsonl": str(self.ruta_jsonl.resolve()),
            "completo": self.completo,
            "casos": [r.a_dict() for r in self.resultados],
            "casos_no_encontrados": self.errores,
            "lineas_sin_caso": self.lineas_sin_caso,
            "informe_guardado": {
                "txt": str(self.informe_txt) if self.informe_txt else None,
                "json": str(self.informe_json) if self.informe_json else None,
            },
        }


def guardar_informe(validacion: ValidacionJsonl) -> None:
    """Escribe el informe en VALIDACIONES_DIR como <jsonl>__<fecha>.txt y .json."""
    carpeta = settings.VALIDACIONES_DIR
    carpeta.mkdir(parents=True, exist_ok=True)
    ahora = datetime.now()
    base = carpeta / f"{validacion.ruta_jsonl.stem}__{ahora.strftime(FORMATO_FECHA)}"
    validacion.informe_txt, validacion.informe_json = (
        base.with_suffix(".txt"),
        base.with_suffix(".json"),
    )
    encabezado = (
        f"JSONL: {validacion.ruta_jsonl.resolve()}\n"
        f"Fecha: {ahora.isoformat(timespec='seconds')}\n\n"
    )
    validacion.informe_txt.write_text(
        encabezado + validacion.informe() + "\n", encoding=CODIFICACION
    )
    validacion.informe_json.write_text(
        json.dumps(validacion.a_dict(), ensure_ascii=False, indent=2), encoding=CODIFICACION
    )


def _agrupar_por_carpeta_real(
    grupos: dict[str, list[ArchivoJsonl]], cliente: ClienteGraph, errores: dict[str, str]
) -> dict[str, tuple[list[str], list[ArchivoJsonl]]]:
    """{carpeta real: (nombres con que la trae el JSONL, archivos)}.

    Dos nombres del JSONL pueden ser la misma carpeta (antes y después de cerrarse el
    caso): se juntan para no dar por faltante lo que está bajo el otro nombre.
    """
    por_carpeta: dict[str, tuple[list[str], list[ArchivoJsonl]]] = {}
    for caso, archivos in grupos.items():
        try:
            real = cliente.resolver_caso(caso)
        except CasoNoEncontradoError as error:
            errores[caso] = str(error)
            continue
        nombres, todos = por_carpeta.setdefault(real, ([], []))
        nombres.append(caso)
        todos.extend(archivos)
    return por_carpeta


def validar_jsonl_contra_sharepoint(
    ruta_jsonl: Path, caso: str | None = None, cliente: ClienteGraph | None = None
) -> ValidacionJsonl:
    """Compara cada caso del JSONL con su carpeta en SharePoint (en vivo, solo lectura) y
    guarda el informe.

    Con `caso`, todo el JSONL se compara contra esa carpeta. Lanza FileNotFoundError,
    CasoDesconocidoError o SharePointError.
    """
    inventario = leer_inventario(ruta_jsonl)
    grupos = {caso: inventario.archivos} if caso else inventario.por_caso()
    sin_caso = grupos.pop(None, [])
    if not grupos:
        raise CasoDesconocidoError(f"{ruta_jsonl.name} no indica el caso: pásalo explícitamente.")

    cliente = cliente or ClienteGraph()
    validacion = ValidacionJsonl(ruta_jsonl=ruta_jsonl, lineas_sin_caso=len(sin_caso))
    for real, (nombres, archivos) in _agrupar_por_carpeta_real(
        grupos, cliente, validacion.errores
    ).items():
        resultado = comparar(
            real, cliente.listar_caso(real), archivos, ignorar=settings.SHAREPOINT_IGNORAR
        )
        otros = [n for n in nombres if n != real]
        resultado.caso_solicitado = "', '".join(otros) or None
        validacion.resultados.append(resultado)

    guardar_informe(validacion)
    return validacion
