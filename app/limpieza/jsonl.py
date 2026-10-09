"""Limpia un JSONL por caso (`Claude-<id>.jsonl`) en memoria, con las reglas 1 a 4.

La regla 5 (enmascarar SSN, cuentas, teléfonos...) NO se aplica: el texto sigue completo.
Nada se escribe en disco ni en SharePoint; el resultado queda en memoria para decidir
después a qué carpeta va cada JSONL.

Por documento:
- Regla 1: si el texto es basura, se vacía `extracted_text` y se anota el motivo en
  `cleaning_discarded_because`. La línea se queda: el archivo existe y cuenta en coverage.
- Reglas 2-4: artefactos del OCR, des-guionado y párrafos, términos legales.

Por JSONL (guía, sección 1): si el mismo `sharepoint_id` está dos veces, se deja una sola
línea (la leída con más texto) y se corrigen `files_described`, `files_read` y `coverage`.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.limpieza.procesador import extraer_confianza, limpiar_texto
from app.limpieza.reglas import motivo_de_descarte

CODIFICACION = "utf-8-sig"
DECIMALES_COVERAGE = 3
REGLAS_APLICADAS = [1, 2, 3, 4]


@dataclass
class ResumenLimpieza:
    documentos: int = 0
    duplicados_quitados: int = 0
    no_leidos: int = 0
    descartados: dict[str, int] = field(default_factory=dict)  # {motivo: documentos}
    limpiados: int = 0
    caracteres_antes: int = 0
    caracteres_despues: int = 0
    lineas_invalidas: int = 0

    @property
    def total_descartados(self) -> int:
        return sum(self.descartados.values())


@dataclass
class JsonlLimpio:
    cabecera: dict[str, Any] | None
    lineas: list[dict[str, Any]]  # las de documento y las demás (matter_context...)
    resumen: ResumenLimpieza

    def contenido(self) -> bytes:
        """El JSONL limpio, listo para guardarlo donde se decida."""
        registros = ([self.cabecera] if self.cabecera else []) + self.lineas
        texto = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in registros)
        return texto.encode("utf-8")


def _id(registro: dict[str, Any]) -> str | None:
    return registro.get("sharepoint_id") or registro.get("id") or None


def _calidad(registro: dict[str, Any]) -> tuple[bool, int]:
    return bool(registro.get("was_read")), len(registro.get("extracted_text") or "")


def _preferida(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """De dos líneas del mismo archivo, la leída y con más texto."""
    return b if _calidad(b) > _calidad(a) else a


def _sin_duplicados(registros: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    por_id: dict[str, int] = {}
    unicos: list[dict[str, Any]] = []
    for registro in registros:
        archivo_id = _id(registro) if registro.get("file_name") else None
        if archivo_id is None or archivo_id not in por_id:
            if archivo_id is not None:
                por_id[archivo_id] = len(unicos)
            unicos.append(registro)
            continue
        posicion = por_id[archivo_id]
        unicos[posicion] = _preferida(unicos[posicion], registro)
    return unicos, len(registros) - len(unicos)


def _limpiar_documento(registro: dict[str, Any], resumen: ResumenLimpieza) -> dict[str, Any]:
    texto = registro.get("extracted_text") or ""
    if not registro.get("was_read") or not texto:
        resumen.no_leidos += not registro.get("was_read")
        return registro
    resumen.caracteres_antes += len(texto)
    motivo = motivo_de_descarte(texto, extraer_confianza(registro))
    if motivo:
        clave = motivo.split(" (")[0]
        resumen.descartados[clave] = resumen.descartados.get(clave, 0) + 1
        return {
            **registro,
            "extracted_text": "",
            "extracted_text_length": 0,
            "cleaning_discarded_because": motivo,
        }
    limpio = limpiar_texto(texto, anonimizar=False)
    resumen.limpiados += 1
    resumen.caracteres_despues += len(limpio)
    return {**registro, "extracted_text": limpio, "extracted_text_length": len(limpio)}


def _cabecera_corregida(
    cabecera: dict[str, Any], documentos: list[dict[str, Any]], resumen: ResumenLimpieza
) -> dict[str, Any]:
    nueva = dict(cabecera)
    nueva["files_described"] = len(documentos)
    nueva["files_read"] = sum(1 for d in documentos if d.get("was_read"))
    en_carpeta = cabecera.get("files_in_matter")
    if en_carpeta:
        nueva["coverage"] = round(len(documentos) / en_carpeta, DECIMALES_COVERAGE)
    nueva["cleaning"] = {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "rules": REGLAS_APLICADAS,
        "pii_masked": False,
        "duplicates_removed": resumen.duplicados_quitados,
        "texts_discarded": resumen.total_descartados,
    }
    return nueva


def _registros(contenido: bytes, resumen: ResumenLimpieza) -> list[dict[str, Any]]:
    registros = []
    for linea in contenido.decode(CODIFICACION, errors="replace").splitlines():
        if not linea.strip():
            continue
        try:
            registros.append(json.loads(linea))
        except json.JSONDecodeError:
            resumen.lineas_invalidas += 1
    return registros


def limpiar_jsonl(contenido: bytes) -> JsonlLimpio:
    """El JSONL limpio en memoria, con su resumen (solo conteos, sin texto)."""
    resumen = ResumenLimpieza()
    registros = _registros(contenido, resumen)
    cabecera = None
    if registros and "matter" in registros[0] and "file_name" not in registros[0]:
        cabecera = registros.pop(0)
    registros, resumen.duplicados_quitados = _sin_duplicados(registros)
    lineas = [_limpiar_documento(r, resumen) if r.get("file_name") else r for r in registros]
    documentos = [r for r in lineas if r.get("file_name")]
    resumen.documentos = len(documentos)
    if cabecera is not None:
        cabecera = _cabecera_corregida(cabecera, documentos, resumen)
    return JsonlLimpio(cabecera, lineas, resumen)
