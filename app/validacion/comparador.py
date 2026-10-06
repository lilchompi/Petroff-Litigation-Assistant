"""Compara los archivos de un caso en SharePoint con los que describe su JSONL.

Se empareja SOLO por `id` de SharePoint: es único y no cambia al renombrar o mover el
archivo dentro de la biblioteca. Si alguien borra un archivo y sube otro con el mismo
nombre, el `id` es otro y la diferencia se ve. Cada línea del JSONL tiene que traerlo;
las que no, se informan aparte como "sin id".
"""

from collections import defaultdict
from dataclasses import dataclass, field
from fnmatch import fnmatch
from typing import Any

from app.sharepoint import ArchivoSharePoint
from app.validacion.inventario_jsonl import ArchivoJsonl

BYTES_POR_MB = 2**20
# El JSONL redondea el tamaño a 2 decimales de MB.
TOLERANCIA_MB = 0.01
CARPETA_RAIZ = "(raíz del caso)"


@dataclass(frozen=True)
class Emparejado:
    jsonl: ArchivoJsonl
    sharepoint: ArchivoSharePoint

    @property
    def movido_o_renombrado(self) -> bool:
        return self.jsonl.ruta.casefold() != self.sharepoint.ruta.casefold()

    @property
    def tamano_distinto(self) -> bool:
        if self.jsonl.tamano_mb is None:
            return False
        mb_sharepoint = self.sharepoint.tamano_bytes / BYTES_POR_MB
        return abs(mb_sharepoint - self.jsonl.tamano_mb) > TOLERANCIA_MB


@dataclass
class ResultadoValidacion:
    caso: str
    total_sharepoint: int
    total_jsonl: int
    emparejados: list[Emparejado] = field(default_factory=list)
    faltantes: list[ArchivoSharePoint] = field(default_factory=list)
    sobrantes: list[ArchivoJsonl] = field(default_factory=list)
    sin_id: list[ArchivoJsonl] = field(default_factory=list)
    duplicados: list[ArchivoJsonl] = field(default_factory=list)
    ignorados: list[ArchivoSharePoint] = field(default_factory=list)
    # El nombre que traía el JSONL, si en SharePoint la carpeta se llama distinto.
    caso_solicitado: str | None = None

    @property
    def completo(self) -> bool:
        return not self.faltantes and not self.sin_id

    @property
    def movidos(self) -> list[Emparejado]:
        return [e for e in self.emparejados if e.movido_o_renombrado]

    @property
    def tamano_distinto(self) -> list[Emparejado]:
        return [e for e in self.emparejados if e.tamano_distinto]

    @property
    def no_leidos(self) -> list[ArchivoJsonl]:
        return [e.jsonl for e in self.emparejados if not e.jsonl.leido]

    def faltantes_por_carpeta(self) -> dict[str, list[ArchivoSharePoint]]:
        grupos: dict[str, list[ArchivoSharePoint]] = defaultdict(list)
        for archivo in sorted(self.faltantes, key=lambda a: (a.carpeta.casefold(), a.nombre)):
            grupos[archivo.carpeta or CARPETA_RAIZ].append(archivo)
        return dict(grupos)

    def resumen_por_carpeta(self) -> list[dict[str, Any]]:
        """Cada carpeta del caso en SharePoint: cuántos archivos tiene, cuántos están en
        el JSONL (por id) y cuántos faltan. Incluye las carpetas completas."""
        conteo: dict[str, dict[str, int]] = defaultdict(lambda: {"en_jsonl": 0, "faltan": 0})
        for emparejado in self.emparejados:
            conteo[emparejado.sharepoint.carpeta]["en_jsonl"] += 1
        for archivo in self.faltantes:
            conteo[archivo.carpeta]["faltan"] += 1
        return [
            {
                "carpeta": carpeta or CARPETA_RAIZ,
                "en_sharepoint": n["en_jsonl"] + n["faltan"],
                "en_jsonl": n["en_jsonl"],
                "faltan": n["faltan"],
            }
            for carpeta, n in sorted(conteo.items(), key=lambda c: c[0].casefold())
        ]

    def a_dict(self) -> dict[str, Any]:
        return {
            "caso": self.caso,
            "caso_solicitado": self.caso_solicitado,
            "completo": self.completo,
            "resumen": {
                "archivos_en_sharepoint": self.total_sharepoint,
                "archivos_en_jsonl": self.total_jsonl,
                "coinciden_por_id": len(self.emparejados),
                "faltan_en_jsonl": len(self.faltantes),
                "sobran_en_jsonl": len(self.sobrantes),
                "lineas_sin_id": len(self.sin_id),
                "ids_duplicados": len(self.duplicados),
                "movidos_o_renombrados": len(self.movidos),
                "tamano_distinto": len(self.tamano_distinto),
                "no_leidos": len(self.no_leidos),
                "ignorados": len(self.ignorados),
            },
            "resumen_por_carpeta": self.resumen_por_carpeta(),
            "faltantes_por_carpeta": {
                carpeta: [
                    {"nombre": a.nombre, "tamano_bytes": a.tamano_bytes, "id": a.id, "url": a.url}
                    for a in archivos
                ]
                for carpeta, archivos in self.faltantes_por_carpeta().items()
            },
            "sobrantes": [{"ruta": a.ruta, "id": a.id, "linea": a.linea} for a in self.sobrantes],
            "sin_id": [{"ruta": a.ruta, "linea": a.linea} for a in self.sin_id],
            "duplicados": [{"ruta": a.ruta, "id": a.id, "linea": a.linea} for a in self.duplicados],
            "movidos_o_renombrados": [
                {
                    "id": e.sharepoint.id,
                    "en_jsonl": e.jsonl.ruta,
                    "en_sharepoint": e.sharepoint.ruta,
                }
                for e in self.movidos
            ],
            "tamano_distinto": [
                {
                    "ruta": e.sharepoint.ruta,
                    "id": e.sharepoint.id,
                    "mb_sharepoint": round(e.sharepoint.tamano_bytes / BYTES_POR_MB, 2),
                    "mb_jsonl": e.jsonl.tamano_mb,
                }
                for e in self.tamano_distinto
            ],
            "no_leidos": [
                {"ruta": a.ruta, "id": a.id, "motivo": a.motivo_no_leido} for a in self.no_leidos
            ],
            "ignorados": [a.ruta for a in self.ignorados],
        }


def _ignorado(archivo: ArchivoSharePoint, patrones: list[str]) -> bool:
    return any(fnmatch(archivo.nombre.casefold(), p.casefold()) for p in patrones)


def comparar(
    caso: str,
    archivos_sharepoint: list[ArchivoSharePoint],
    archivos_jsonl: list[ArchivoJsonl],
    ignorar: list[str] | None = None,
) -> ResultadoValidacion:
    patrones = ignorar or []
    ignorados = [a for a in archivos_sharepoint if _ignorado(a, patrones)]
    pendientes = {a.id: a for a in archivos_sharepoint if not _ignorado(a, patrones)}
    resultado = ResultadoValidacion(
        caso=caso,
        total_sharepoint=len(pendientes),
        total_jsonl=len(archivos_jsonl),
        ignorados=ignorados,
    )

    vistos: set[str] = set()
    for archivo in archivos_jsonl:
        if not archivo.id:
            resultado.sin_id.append(archivo)
        elif archivo.id in vistos:
            resultado.duplicados.append(archivo)
        elif archivo.id in pendientes:
            resultado.emparejados.append(Emparejado(archivo, pendientes.pop(archivo.id)))
        else:
            resultado.sobrantes.append(archivo)
        if archivo.id:
            vistos.add(archivo.id)

    resultado.faltantes = list(pendientes.values())
    return resultado
