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
from app.revision.reglas import Reglas, cargar_reglas
from app.servicios.validacion import ValidacionJsonl, validar_inventario
from app.sharepoint import ClienteGraph, SharePointError
from app.validacion import InventarioJsonl, leer_inventario_de_bytes

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
    matters: IndiceMatters | None = None
    # carpeta_id -> {archivos_sharepoint, archivos_jsonl, faltan} de los JSONL revisados
    cobertura: dict[str, dict[str, int]] = field(default_factory=dict)


def leer_jsonl_de_carpetas(cliente: ClienteGraph, carpetas: list[str]) -> list[InventarioJsonl]:
    """Lee los JSONL de varias carpetas. Si un caso está en más de una (mismo
    sharepoint_folder_id), se queda con el JSONL generado más recientemente."""
    por_caso: dict[str, InventarioJsonl] = {}
    for carpeta in carpetas:
        for inventario in leer_jsonl_de_sharepoint(cliente, carpeta):
            clave = inventario.id_carpeta or str(inventario.ruta)
            actual = por_caso.get(clave)
            if actual is None or _generado(inventario) > _generado(actual):
                por_caso[clave] = inventario
    return list(por_caso.values())


def _generado(inventario: InventarioJsonl) -> str:
    return str((inventario.cabecera or {}).get("generated", ""))


def leer_jsonl_de_sharepoint(cliente: ClienteGraph, ruta_sharepoint: str) -> list[InventarioJsonl]:
    """Lee los .jsonl de una carpeta de SharePoint en memoria, sin guardar nada en disco.

    De cada JSONL se conservan solo los datos de sus archivos y sus index; el texto extraído
    (que es lo que pesa y lleva datos personales) se descarta al leerlo.
    """
    inventarios = []
    for item in sorted(cliente.hijos_de_ruta(ruta_sharepoint), key=lambda x: x["name"]):
        if "folder" in item or not item["name"].casefold().endswith(".jsonl"):
            continue
        contenido = cliente.descargar(item["id"])
        inventarios.append(leer_inventario_de_bytes(contenido, f"{ruta_sharepoint}/{item['name']}"))
    return inventarios


def _citas(inventarios: list[InventarioJsonl], reglas: Reglas) -> set[str]:
    """Las citas configuradas más los index que salen en las carátulas de muchos casos."""
    por_cliente: dict[str, set[str]] = {}
    for inventario in inventarios:
        nombre = leer_nombre((inventario.cabecera or {}).get("matter", ""))
        indices = {i for a in inventario.archivos for i in a.indices_caratula} - {nombre.index}
        cliente = " ".join(sorted(nombre.palabras_cliente)) or str(inventario.ruta)
        por_cliente.setdefault(cliente, set()).update(indices)
    return set(reglas.citas_conocidas) | citas_del_lote(
        por_cliente, reglas.minimo_clientes_para_cita
    )


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


def _cobertura(validacion: ValidacionJsonl, carpeta_id: str) -> dict[str, int]:
    resultados = validacion.resultados
    return {
        "archivos_sharepoint": sum(r.total_sharepoint for r in resultados),
        "archivos_jsonl": sum(r.total_jsonl for r in resultados),
        "faltan": sum(len(r.faltantes) for r in resultados) + (0 if resultados else 1),
        "carpeta_id": carpeta_id,
    }


def revisar_lote(
    inventarios: list[InventarioJsonl], cliente: ClienteGraph | None = None
) -> ResultadoRevision:
    """Valida cada JSONL contra SharePoint y aplica las reglas. Solo lee; devuelve el plan."""
    cliente = cliente or ClienteGraph()
    matters = IndiceMatters(cliente.carpetas_de_casos())
    reglas = cargar_reglas()
    revision = Revision(matters, citas=_citas(inventarios, reglas), reglas=reglas)
    revision.plan.reglas = reglas.version
    resultado = ResultadoRevision(plan=revision.plan, matters=matters)
    for inventario in inventarios:
        nombre = inventario.ruta.name
        carpeta_id = _id_carpeta(inventario, matters)
        if carpeta_id is None:
            resultado.errores[nombre] = "no se encontró su carpeta en Matters/"
            continue
        try:
            validacion = validar_inventario(inventario, cliente=cliente)
            resultado.validaciones.append(validacion)
            resultado.cobertura[carpeta_id] = _cobertura(validacion, carpeta_id)
        except (SharePointError, ValueError) as error:
            resultado.errores[nombre] = str(error)
        revision.revisar(carpeta_id, inventario.archivos)
    revision.cerrar()
    _guardar(resultado)
    return resultado
