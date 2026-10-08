"""Aplica un Plan en SharePoint dejando un diario, y deshace lo aplicado con ese diario.

El diario es el respaldo: una línea por cada cambio hecho, con el estado de antes y el de
después, escrita y guardada en disco justo después de cada cambio. Con él se puede revertir
todo en orden inverso. Se renombra, se mueve (dentro de la misma biblioteca, conservando el id
y el historial de versiones) y, al fusionar, se elimina la carpeta vieja cuando ya quedó
vacía; eliminar la manda a la papelera de SharePoint y el diario permite recrearla.

Antes de cada acción se comprueba que la carpeta siga como estaba cuando se hizo el plan.
Si alguien la cambió entretanto, la acción se salta. Ante cualquier error se para todo, para
que lo hecho hasta ahí se pueda revisar o deshacer.
"""

import json
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.revision.plan import FUSIONAR, RENOMBRAR, Accion, Plan, ahora
from app.sharepoint import ClienteGraph, SharePointError

logger = logging.getLogger(__name__)

CODIFICACION = "utf-8"
OP_RENOMBRAR = "renombrar"
OP_MOVER = "mover"
OP_CREAR_CARPETA = "crear_carpeta"
OP_ELIMINAR_CARPETA = "eliminar_carpeta"


class PlanDesactualizadoError(RuntimeError):
    """La carpeta ya no está como cuando se generó el plan."""


@dataclass
class Resultado:
    hechas: list[str] = field(default_factory=list)
    saltadas: list[str] = field(default_factory=list)
    error: str | None = None
    cambios: int = 0
    aplicadas: list[Accion] = field(default_factory=list)


class Diario:
    """El respaldo: un JSONL que se escribe y se fuerza a disco cambio por cambio."""

    def __init__(self, ruta: Path) -> None:
        self.ruta = ruta
        self._secuencia = 0
        ruta.parent.mkdir(parents=True, exist_ok=True)

    def anotar(self, op: str, item_id: str, antes: dict, despues: dict, accion: str) -> None:
        self._secuencia += 1
        linea = {
            "seq": self._secuencia,
            "momento": ahora(),
            "accion": accion,
            "op": op,
            "item_id": item_id,
            "antes": antes,
            "despues": despues,
        }
        with self.ruta.open("a", encoding=CODIFICACION) as archivo:
            archivo.write(json.dumps(linea, ensure_ascii=False) + "\n")
            archivo.flush()
            os.fsync(archivo.fileno())

    def cambios(self) -> int:
        return self._secuencia

    @staticmethod
    def leer(ruta: Path) -> list[dict[str, Any]]:
        lineas = ruta.read_text(encoding=CODIFICACION).splitlines()
        return [json.loads(linea) for linea in lineas if linea.strip()]


class Ejecutor:
    def __init__(
        self,
        cliente: ClienteGraph,
        diario: Diario,
        simular: bool = True,
        avisar: Callable[[str], None] = logger.info,
    ) -> None:
        self.cliente = cliente
        self.diario = diario
        self.simular = simular
        self.avisar = avisar

    # ------------------------------------------------------------------ helpers

    def _comprobar(self, item_id: str, nombre_esperado: str) -> dict:
        actual = self.cliente.obtener(item_id)
        if actual["name"] != nombre_esperado:
            raise PlanDesactualizadoError(
                f"'{nombre_esperado}' ahora se llama '{actual['name']}': se regenera el plan."
            )
        return actual

    def _renombrar(self, item_id: str, antes: str, despues: str, accion: str) -> None:
        self.avisar(f"    renombrar '{antes}' -> '{despues}'")
        if self.simular:
            return
        self.cliente.renombrar(item_id, despues)
        self.diario.anotar(OP_RENOMBRAR, item_id, {"nombre": antes}, {"nombre": despues}, accion)

    def _mover(self, hijo: dict, padre_antes: str, padre_despues: str, accion: str) -> None:
        self.avisar(f"    mover '{hijo['name']}'")
        if self.simular:
            return
        self.cliente.mover(hijo["id"], padre_despues)
        self.diario.anotar(
            OP_MOVER,
            hijo["id"],
            {"padre": padre_antes, "nombre": hijo["name"]},
            {"padre": padre_despues},
            accion,
        )

    def _carpeta(self, padre_id: str, nombre: str, accion: str) -> str:
        self.avisar(f"    carpeta '{nombre}'")
        if self.simular:
            return f"(simulada:{nombre})"
        carpeta_id, creada = self.cliente.crear_carpeta(padre_id, nombre)
        if creada:
            self.diario.anotar(
                OP_CREAR_CARPETA, carpeta_id, {}, {"padre": padre_id, "nombre": nombre}, accion
            )
        return carpeta_id

    # ------------------------------------------------------------------ acciones

    def _aplicar_renombrar(self, accion: Accion, etiqueta: str) -> None:
        d = accion.datos
        self._comprobar(d["carpeta_id"], d["nombre_actual"])
        self._renombrar(d["carpeta_id"], d["nombre_actual"], d["nombre_nuevo"], etiqueta)

    def _eliminar_si_vacia(self, carpeta_id: str, nombre: str, accion: str) -> None:
        """La carpeta vieja se elimina solo si quedó vacía. Va a la papelera de SharePoint."""
        self.avisar(f"    eliminar la carpeta vacía '{nombre}'")
        if self.simular:
            return
        restantes = self.cliente.hijos(carpeta_id)
        if restantes:
            raise SharePointError(
                f"'{nombre}' no quedó vacía ({len(restantes)} elementos): no se elimina."
            )
        padre = self.cliente.obtener(carpeta_id).get("parentReference", {}).get("id")
        self.cliente.eliminar(carpeta_id)
        self.diario.anotar(
            OP_ELIMINAR_CARPETA, carpeta_id, {"nombre": nombre, "padre": padre}, {}, accion
        )

    def _aplicar_fusionar(self, accion: Accion, etiqueta: str) -> None:
        """Mueve TODO el contenido de la carpeta vieja (su JSONL incluido) y la elimina."""
        d = accion.datos
        self._comprobar(d["origen_id"], d["origen_nombre"])
        self._comprobar(d["destino_id"], d["destino_nombre"])
        padre = d["destino_id"]
        for nombre in d["subcarpeta"]:
            padre = self._carpeta(padre, nombre, etiqueta)
        for hijo in self.cliente.hijos(d["origen_id"]):
            self._mover(hijo, d["origen_id"], padre, etiqueta)
        self._eliminar_si_vacia(d["origen_id"], d["origen_nombre"], etiqueta)

    def aplicar(self, plan: Plan) -> Resultado:
        resultado = Resultado()
        for numero, accion in enumerate(plan.acciones, 1):
            etiqueta = f"{numero}:{accion.tipo}:{accion.regla}"
            titulo = accion.datos.get("nombre_actual") or accion.datos.get("origen_nombre")
            self.avisar(f"[{numero}/{len(plan.acciones)}] {accion.tipo}: {titulo}")
            try:
                if accion.tipo == RENOMBRAR:
                    self._aplicar_renombrar(accion, etiqueta)
                elif accion.tipo == FUSIONAR:
                    self._aplicar_fusionar(accion, etiqueta)
            except PlanDesactualizadoError as error:
                resultado.saltadas.append(f"{etiqueta}: {error}")
                continue
            except SharePointError as error:
                resultado.error = f"{etiqueta}: {error}"
                break
            resultado.hechas.append(etiqueta)
            if not self.simular:
                resultado.aplicadas.append(accion)
        resultado.cambios = self.diario.cambios()
        return resultado


def lineas_del_diario(ruta_diario: Path, tipos: set[str] | None = None) -> list[dict[str, Any]]:
    """Las líneas del diario, opcionalmente solo las de ciertos tipos de acción.

    La etiqueta de cada línea es '<n>:<tipo>:<regla>' (p. ej. '3:fusionar:6_ocr_...').
    """
    lineas = Diario.leer(ruta_diario)
    if not tipos:
        return lineas
    return [linea for linea in lineas if linea["accion"].split(":")[1] in tipos]


def deshacer(
    cliente: ClienteGraph,
    ruta_diario: Path,
    simular: bool = True,
    avisar: Callable[[str], None] = logger.info,
    tipos: set[str] | None = None,
) -> Resultado:
    """Revierte el diario en orden inverso. Solo revierte lo que sigue como lo dejó el plan.

    Una carpeta eliminada se vuelve a crear con su nombre y en su sitio (con un id nuevo), y
    sus archivos vuelven a ella. Las carpetas que creó la fusión se eliminan si quedan vacías.
    Con `tipos` (p. ej. {"fusionar"}) solo se revierten los cambios de esas acciones.
    """
    resultado = Resultado()
    reemplazos: dict[str, str] = {}  # id de carpeta eliminada -> id de la carpeta recreada
    for linea in reversed(lineas_del_diario(ruta_diario, tipos)):
        etiqueta = f"#{linea['seq']} {linea['op']}"
        try:
            hecho = _revertir(cliente, linea, simular, avisar, reemplazos)
        except SharePointError as error:
            resultado.error = f"{etiqueta}: {error}"
            break
        (resultado.hechas if hecho else resultado.saltadas).append(etiqueta)
    return resultado


def _revertir_creada(
    cliente: ClienteGraph, item_id: str, nombre: str, simular: bool, avisar
) -> bool:
    if not simular and cliente.hijos(item_id):
        avisar(f"    la carpeta '{nombre}' tiene contenido nuevo: no se elimina")
        return False
    avisar(f"    eliminar la carpeta creada por la fusión '{nombre}'")
    if not simular:
        cliente.eliminar(item_id)
    return True


def _revertir_eliminada(
    cliente: ClienteGraph, linea: dict, simular: bool, avisar, reemplazos: dict[str, str]
) -> bool:
    antes = linea["antes"]
    avisar(f"    volver a crear la carpeta '{antes['nombre']}'")
    if simular:
        reemplazos[linea["item_id"]] = linea["item_id"]
        return True
    nuevo_id, _ = cliente.crear_carpeta(antes["padre"], antes["nombre"])
    reemplazos[linea["item_id"]] = nuevo_id
    return True


def _revertir_movido(
    cliente: ClienteGraph, linea: dict, simular: bool, avisar, reemplazos: dict[str, str]
) -> bool:
    actual = cliente.obtener(linea["item_id"])
    if actual.get("parentReference", {}).get("id") != linea["despues"]["padre"]:
        avisar(f"    '{actual['name']}' ya no está donde lo dejó el plan: no se toca")
        return False
    avisar(f"    devolver '{actual['name']}' a su carpeta original")
    if not simular:
        padre = linea["antes"]["padre"]
        cliente.mover(linea["item_id"], reemplazos.get(padre, padre))
    return True


def _revertir(
    cliente: ClienteGraph, linea: dict, simular: bool, avisar: Callable, reemplazos: dict
) -> bool:
    item_id, antes, despues = linea["item_id"], linea["antes"], linea["despues"]
    if linea["op"] == OP_CREAR_CARPETA:
        return _revertir_creada(cliente, item_id, despues["nombre"], simular, avisar)
    if linea["op"] == OP_ELIMINAR_CARPETA:
        return _revertir_eliminada(cliente, linea, simular, avisar, reemplazos)
    if linea["op"] == OP_MOVER:
        return _revertir_movido(cliente, linea, simular, avisar, reemplazos)
    actual = cliente.obtener(item_id)
    if actual["name"] != despues["nombre"]:
        avisar(f"    '{actual['name']}' cambió después del plan: no se toca")
        return False
    avisar(f"    renombrar '{despues['nombre']}' -> '{antes['nombre']}'")
    if not simular:
        cliente.renombrar(item_id, antes["nombre"])
    return True
