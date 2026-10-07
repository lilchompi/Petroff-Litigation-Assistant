"""Revisión de calidad de un lote de JSONL por caso: genera el plan, sin tocar SharePoint."""

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from app.core.config import settings
from app.revision.motor import IndiceMatters, Revision, citas_del_lote
from app.revision.nombres import leer_nombre
from app.revision.plan import Plan
from app.servicios.validacion import ValidacionJsonl, validar_jsonl_contra_sharepoint
from app.sharepoint import ClienteGraph, SharePointError
from app.validacion import InventarioJsonl, leer_inventario

FORMATO_FECHA = "%Y%m%d-%H%M%S"
CODIFICACION = "utf-8"
CARACTERES_NO_VALIDOS = re.compile(r'[<>:"/\\|?*]')


@dataclass
class ResultadoRevision:
    plan: Plan
    validaciones: list[ValidacionJsonl] = field(default_factory=list)
    errores: dict[str, str] = field(default_factory=dict)
    ruta_plan: Path | None = None
    ruta_informe: Path | None = None
    ruta_hallazgos: Path | None = None


def descargar_jsonl(cliente: ClienteGraph, ruta_sharepoint: str, destino: Path) -> list[Path]:
    """Baja los .jsonl de una carpeta de SharePoint. Llevan datos personales: van a salida/."""
    destino.mkdir(parents=True, exist_ok=True)
    rutas = []
    for item in cliente.hijos_de_ruta(ruta_sharepoint):
        if "folder" in item or not item["name"].casefold().endswith(".jsonl"):
            continue
        ruta = destino / item["name"]
        ruta.write_bytes(cliente.descargar(item["id"]))
        rutas.append(ruta)
    return sorted(rutas)


def _citas(inventarios: list[InventarioJsonl]) -> set[str]:
    """Las citas configuradas más los index que salen en las carátulas de muchos casos."""
    por_cliente: dict[str, set[str]] = {}
    for inventario in inventarios:
        nombre = leer_nombre((inventario.cabecera or {}).get("matter", ""))
        indices = {i for a in inventario.archivos for i in a.indices_caratula} - {nombre.index}
        cliente = " ".join(sorted(nombre.palabras_cliente)) or str(inventario.ruta)
        por_cliente.setdefault(cliente, set()).update(indices)
    return set(settings.INDEX_CITAS) | citas_del_lote(por_cliente, settings.MINIMO_CASOS_CITA)


def _id_carpeta(inventario: InventarioJsonl, matters: IndiceMatters) -> str | None:
    if inventario.id_carpeta:
        return inventario.id_carpeta
    nombre = (inventario.cabecera or {}).get("matter")
    return next((c.id for c in matters.por_item.values() if c.titulo == nombre), None)


def _guardar(resultado: ResultadoRevision) -> None:
    carpeta = settings.REVISION_DIR
    fecha = datetime.now().strftime(FORMATO_FECHA)
    resultado.ruta_plan = carpeta / f"plan__{fecha}.json"
    resultado.plan.guardar(resultado.ruta_plan)
    # Las líneas review_finding, por caso, listas para añadirlas a su JSONL.
    resultado.ruta_hallazgos = carpeta / f"hallazgos__{fecha}"
    resultado.ruta_hallazgos.mkdir(parents=True, exist_ok=True)
    for hallazgo in resultado.plan.hallazgos:
        nombre = CARACTERES_NO_VALIDOS.sub("_", hallazgo.carpeta)
        ruta = resultado.ruta_hallazgos / f"{nombre}.review_findings.jsonl"
        with ruta.open("a", encoding=CODIFICACION) as archivo:
            linea = json.dumps(hallazgo.como_review_finding(), ensure_ascii=False)
            archivo.write(linea + "\n")


def revisar_lote(rutas: list[Path], cliente: ClienteGraph | None = None) -> ResultadoRevision:
    """Valida cada JSONL contra SharePoint y aplica las reglas. Solo lee; devuelve el plan."""
    cliente = cliente or ClienteGraph()
    inventarios = [leer_inventario(r) for r in rutas]
    matters = IndiceMatters(cliente.carpetas_de_casos())
    revision = Revision(matters, citas=_citas(inventarios))
    resultado = ResultadoRevision(plan=revision.plan)
    for ruta, inventario in zip(rutas, inventarios, strict=True):
        try:
            resultado.validaciones.append(validar_jsonl_contra_sharepoint(ruta, cliente=cliente))
        except (FileNotFoundError, SharePointError, ValueError) as error:
            resultado.errores[ruta.name] = str(error)
        carpeta_id = _id_carpeta(inventario, matters)
        if carpeta_id is None:
            resultado.errores[ruta.name] = "no se encontró su carpeta en Matters/"
            continue
        revision.revisar(carpeta_id, inventario.archivos)
    revision.cerrar()
    _guardar(resultado)
    return resultado
