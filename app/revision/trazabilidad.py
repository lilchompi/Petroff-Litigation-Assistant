"""Trazabilidad de la limpieza de Matters/: en qué estado está cada carpeta de caso.

Tres archivos en salida/revision/:
- trazabilidad.csv  una fila por carpeta de Matters/ con su estado (se abre en Excel).
- trazabilidad.log  un renglón por evento: revisión, cambio aplicado, cambio deshecho.
- progreso.txt      el resumen con porcentajes, rehecho en cada evento.

Se actualiza sola: al revisar (revisar_matters), al aplicar (aplicar_plan) y al deshacer
(deshacer_plan). Las carpetas que no tienen JSONL todavía quedan "pendiente: sin JSONL".
"""

import csv
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.revision.nombres import leer_nombre
from app.revision.plan import FUSIONAR, RENOMBRAR, Accion, Plan, ahora

CODIFICACION = "utf-8-sig"
PORCENTAJE = 100

LIMPIA = "limpia"
COMPLEJA = "revisar: casos complejos (LLM o persona)"
POR_APLICAR = "pendiente: aplicar plan"
INCOMPLETA = "pendiente: JSONL incompleto"
SIN_JSONL = "pendiente: sin JSONL"
DESHECHA = "pendiente: volver a revisar (se deshizo un cambio)"
FUSIONADA = "fusionada (carpeta eliminada)"
ORDEN_ESTADOS = [LIMPIA, COMPLEJA, POR_APLICAR, INCOMPLETA, DESHECHA, SIN_JSONL, FUSIONADA]

COLUMNAS = [
    "carpeta_id",
    "carpeta",
    "id_interno",
    "index",
    "estado",
    "tiene_jsonl",
    "archivos_sharepoint",
    "archivos_jsonl",
    "faltan_en_jsonl",
    "acciones_pendientes",
    "acciones_aplicadas",
    "casos_complejos",
    "avisos",
    "fusionada_en",
    "ultima_revision",
    "ultimo_cambio",
]
NUMERICAS = (
    "archivos_sharepoint",
    "archivos_jsonl",
    "faltan_en_jsonl",
    "acciones_pendientes",
    "acciones_aplicadas",
    "casos_complejos",
    "avisos",
)


def _fila_nueva(carpeta_id: str, titulo: str) -> dict[str, Any]:
    fila: dict[str, Any] = dict.fromkeys(COLUMNAS, "")
    fila.update(dict.fromkeys(NUMERICAS, 0))
    fila.update(carpeta_id=carpeta_id, tiene_jsonl="no", estado=SIN_JSONL)
    _poner_nombre(fila, titulo)
    return fila


def _poner_nombre(fila: dict[str, Any], titulo: str) -> None:
    nombre = leer_nombre(titulo)
    fila.update(carpeta=titulo, id_interno=nombre.id_interno or "", index=nombre.index or "")


def _estado(fila: dict[str, Any]) -> str:
    if fila["estado"] in (FUSIONADA, DESHECHA):
        return fila["estado"]
    if fila["tiene_jsonl"] != "si":
        return SIN_JSONL
    if fila["faltan_en_jsonl"]:
        return INCOMPLETA
    if fila["acciones_pendientes"]:
        return POR_APLICAR
    return COMPLEJA if fila["casos_complejos"] else LIMPIA


class Trazabilidad:
    def __init__(self, carpeta: Path | None = None) -> None:
        carpeta = carpeta or settings.REVISION_DIR
        self.ruta_csv = carpeta / "trazabilidad.csv"
        self.ruta_log = carpeta / "trazabilidad.log"
        self.ruta_progreso = carpeta / "progreso.txt"
        self.filas: dict[str, dict[str, Any]] = {}
        if self.ruta_csv.exists():
            with self.ruta_csv.open(encoding=CODIFICACION, newline="") as archivo:
                for fila in csv.DictReader(archivo):
                    fila.update({c: int(fila[c] or 0) for c in NUMERICAS})
                    self.filas[fila["carpeta_id"]] = fila

    # ------------------------------------------------------------------ eventos

    def log(self, evento: str, detalle: str) -> None:
        self.ruta_log.parent.mkdir(parents=True, exist_ok=True)
        with self.ruta_log.open("a", encoding="utf-8") as archivo:
            archivo.write(f"{ahora()}  {evento:<10}  {detalle}\n")

    def sincronizar(self, carpetas: dict[str, str]) -> None:
        """Alinea las filas con las carpetas que hay hoy en Matters/ ({id: nombre})."""
        for carpeta_id, titulo in carpetas.items():
            fila = self.filas.setdefault(carpeta_id, _fila_nueva(carpeta_id, titulo))
            if fila["carpeta"] != titulo:
                _poner_nombre(fila, titulo)
        for carpeta_id in [i for i in self.filas if i not in carpetas]:
            if self.filas[carpeta_id]["estado"] != FUSIONADA:
                del self.filas[carpeta_id]  # ya no existe (y no por una fusión nuestra)

    def registrar_revision(
        self, plan: Plan, cobertura: dict[str, dict[str, int]], ids_por_titulo: dict[str, str]
    ) -> None:
        pendientes = Counter(i for a in plan.acciones for i in _carpetas_de(a))
        complejos, avisos = Counter(), Counter()
        for h in plan.hallazgos:
            carpeta_id = ids_por_titulo.get(h.carpeta)
            if carpeta_id and h.para_llm:
                complejos[carpeta_id] += 1
            elif carpeta_id and not h.regla.endswith(("_seguimiento", "_hubspot", "_informativo")):
                avisos[carpeta_id] += 1
        for carpeta_id, datos in cobertura.items():
            fila = self.filas.get(carpeta_id)
            if fila is None or fila["estado"] == FUSIONADA:
                continue
            fila.update(
                tiene_jsonl="si",
                archivos_sharepoint=datos["archivos_sharepoint"],
                archivos_jsonl=datos["archivos_jsonl"],
                faltan_en_jsonl=datos["faltan"],
                acciones_pendientes=pendientes[carpeta_id],
                casos_complejos=complejos[carpeta_id],
                avisos=avisos[carpeta_id],
                ultima_revision=plan.generado,
                estado="",
            )
            fila["estado"] = _estado(fila)
        self.log(
            "REVISION",
            f"{len(cobertura)} JSONL revisados: {len(plan.acciones)} acciones, "
            f"{len(plan.hallazgos)} hallazgos",
        )

    def registrar_aplicadas(self, acciones: Iterable[Accion]) -> None:
        for accion in acciones:
            d = accion.datos
            if accion.tipo == RENOMBRAR:
                self._aplicada(d["carpeta_id"])
                _poner_nombre(self.filas[d["carpeta_id"]], d["nombre_nuevo"])
                self.log("APLICADO", f"renombrar '{d['nombre_actual']}' -> '{d['nombre_nuevo']}'")
            elif accion.tipo == FUSIONAR:
                self._aplicada(d["destino_id"])
                origen = self._aplicada(d["origen_id"])
                if origen is not None:
                    origen.update(estado=FUSIONADA, fusionada_en=d["destino_nombre"])
                self.log("APLICADO", f"fusionar '{d['origen_nombre']}' en '{d['destino_nombre']}'")

    def _aplicada(self, carpeta_id: str) -> dict[str, Any] | None:
        fila = self.filas.get(carpeta_id)
        if fila is None:
            return None
        fila["acciones_pendientes"] = max(0, fila["acciones_pendientes"] - 1)
        fila["acciones_aplicadas"] += 1
        fila["ultimo_cambio"] = ahora()
        fila["estado"] = _estado(fila)
        return fila

    def registrar_deshecho(self, lineas_diario: list[dict[str, Any]]) -> None:
        for linea in lineas_diario:
            fila = self.filas.get(linea["item_id"])
            if fila is not None and linea["op"] in ("renombrar", "eliminar_carpeta"):
                fila.update(estado=DESHECHA, ultimo_cambio=ahora())
                if linea["op"] == "renombrar":
                    _poner_nombre(fila, linea["antes"]["nombre"])
        self.log("DESHECHO", f"{len(lineas_diario)} cambios del diario revertidos")

    # ------------------------------------------------------------------ salida

    def resumen(self) -> list[str]:
        estados = Counter(f["estado"] for f in self.filas.values())
        vivas = len(self.filas) - estados[FUSIONADA]
        con_jsonl = sum(1 for f in self.filas.values() if f["tiene_jsonl"] == "si")

        def pct(n: int) -> str:
            return f"{PORCENTAJE * n / vivas:5.1f}%" if vivas else "  0.0%"

        lineas = [
            f"Progreso de la limpieza de Matters/ — {ahora()}",
            "=" * 66,
            f"  Carpetas de caso:          {vivas}",
            f"  LIMPIAS:                   {estados[LIMPIA]:>5}   {pct(estados[LIMPIA])}",
            f"  Con JSONL revisado:        {con_jsonl:>5}   {pct(con_jsonl)}",
            "",
            "  Por estado:",
        ]
        lineas += [f"    {e:<52} {estados[e]:>5}" for e in ORDEN_ESTADOS if estados[e]]
        return lineas

    def guardar(self) -> None:
        self.ruta_csv.parent.mkdir(parents=True, exist_ok=True)
        ordenadas = sorted(
            self.filas.values(), key=lambda f: (ORDEN_ESTADOS.index(f["estado"]), f["carpeta"])
        )
        with self.ruta_csv.open("w", encoding=CODIFICACION, newline="") as archivo:
            escritor = csv.DictWriter(archivo, fieldnames=COLUMNAS)
            escritor.writeheader()
            escritor.writerows(ordenadas)
        self.ruta_progreso.write_text("\n".join(self.resumen()) + "\n", encoding="utf-8")


def _carpetas_de(accion: Accion) -> list[str]:
    d = accion.datos
    return [d["carpeta_id"]] if accion.tipo == RENOMBRAR else [d["origen_id"], d["destino_id"]]
