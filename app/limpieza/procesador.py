"""Aplica las 5 reglas de limpieza a un registro del JSONL de OCR."""

from typing import Any

from app.core.constantes import PORCENTAJE
from app.limpieza import patrones
from app.limpieza.reglas import (
    anonimizar_pii,
    desguionar,
    eliminar_artefactos_ocr,
    motivo_de_descarte,
    normalizar_terminos_legales,
    unificar_parrafos,
)

CONFIANZA_MAXIMA_EN_FRACCION = 1.0


def _extraer_texto_crudo(registro: dict[str, Any]) -> str:
    return registro.get("extracted_text") or registro.get("texto_pagina") or ""


def _confianza_desde_descripcion_ocr(descripcion: str) -> float | None:
    """Extrae la confianza de textos como 'PaddleOCR (mean confidence 0.99)' en escala 0-100."""
    coincidencia = patrones.CONFIANZA_EN_DESCRIPCION_OCR.search(descripcion)
    if not coincidencia:
        return None
    valor = float(coincidencia.group(1))
    return valor * PORCENTAJE if valor <= CONFIANZA_MAXIMA_EN_FRACCION else valor


def _extraer_confianza(registro: dict[str, Any]) -> float | None:
    confianza = registro.get("confianza_pagina") or registro.get("confianza_promedio")
    if confianza is None and registro.get("read_with"):
        return _confianza_desde_descripcion_ocr(str(registro["read_with"]))
    return confianza


def limpiar_texto(texto_crudo: str) -> str:
    """Aplica las reglas 2 a 5 y compacta los saltos de línea repetidos."""
    texto = eliminar_artefactos_ocr(texto_crudo)
    texto = unificar_parrafos(desguionar(texto))
    texto = normalizar_terminos_legales(texto)
    texto = anonimizar_pii(texto)
    return patrones.SALTOS_DE_LINEA_EXCESIVOS.sub(patrones.SEPARADOR_DE_PARRAFO, texto).strip()


def procesar_registro_ocr(registro: dict[str, Any]) -> dict[str, Any]:
    """Devuelve el registro enriquecido con `se_descarta`, `motivo_descarte`,
    `texto_limpio` y `metricas_limpieza`."""
    texto_crudo = _extraer_texto_crudo(registro)
    motivo = motivo_de_descarte(texto_crudo, _extraer_confianza(registro))

    if motivo:
        return {
            **registro,
            "se_descarta": True,
            "motivo_descarte": motivo,
            "texto_limpio": None,
            "metricas_limpieza": {"chars_originales": len(texto_crudo), "chars_limpios": 0},
        }

    texto_limpio = limpiar_texto(texto_crudo)
    return {
        **registro,
        "se_descarta": False,
        "motivo_descarte": None,
        "texto_limpio": texto_limpio,
        "metricas_limpieza": {
            "chars_originales": len(texto_crudo),
            "chars_limpios": len(texto_limpio),
            "contiene_pii_anonimizada": bool(patrones.MARCA_PII_ANONIMIZADA.search(texto_limpio)),
        },
    }
