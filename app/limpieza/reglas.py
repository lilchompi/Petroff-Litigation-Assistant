"""Las 5 reglas de limpieza OCR de Petroff Amshen LLP.

- Regla 1: Filtro de descarte (evitar "Garbage In, Garbage Out").
- Regla 2: Eliminación de artefactos de PaddleOCR y Unicode roto.
- Regla 3: Des-guionado y unificación de párrafos.
- Regla 4: Normalización de términos legales críticos.
- Regla 5: Anonimización de PII preservando los últimos 4 dígitos.
"""

import re

from app.core.constantes import PORCENTAJE
from app.limpieza import patrones
from app.limpieza.terminos_legales import TERMINOS_NORMALIZADOS

MINIMO_CARACTERES = 25
CONFIANZA_MINIMA = 45.0
PROPORCION_MAXIMA_SIMBOLOS = 0.40
FINALES_DE_ORACION = (".", ":", ";", "!", "?")


def _confianza_es_conocida(confianza: float | None) -> bool:
    return confianza is not None and confianza > 0


def motivo_de_descarte(texto: str, confianza_promedio: float | None) -> str | None:
    """Regla 1: devuelve el motivo por el que el texto se descarta, o None si es aprovechable."""
    if not texto:
        return "Texto vacío"

    total_caracteres = len(texto.strip())
    if total_caracteres < MINIMO_CARACTERES:
        return f"total_caracteres < {MINIMO_CARACTERES} ({total_caracteres} chars)"

    if _confianza_es_conocida(confianza_promedio) and confianza_promedio < CONFIANZA_MINIMA:
        return f"confianza_promedio < {CONFIANZA_MINIMA} ({confianza_promedio:.1f}%)"

    total_simbolos = len(patrones.SIMBOLO_NO_ALFANUMERICO.findall(texto))
    proporcion_simbolos = total_simbolos / total_caracteres
    if proporcion_simbolos > PROPORCION_MAXIMA_SIMBOLOS:
        return (
            f"Más del {PROPORCION_MAXIMA_SIMBOLOS * PORCENTAJE:.0f}% de símbolos no "
            f"alfanuméricos ({proporcion_simbolos * PORCENTAJE:.1f}%)"
        )

    return None


def eliminar_artefactos_ocr(texto: str) -> str:
    """Regla 2: quita caracteres asiáticos, de control, Unicode roto y líneas de relleno."""
    sin_asiaticos = patrones.CARACTERES_ASIATICOS.sub("", texto)
    sin_control = patrones.CARACTERES_CONTROL_Y_UNICODE_ROTO.sub(" ", sin_asiaticos)
    return patrones.LINEA_DE_RELLENO.sub("", sin_control)


def desguionar(texto: str) -> str:
    """Regla 3a: une palabras cortadas con guion al final de línea (juris-\\ndiction)."""
    return patrones.PALABRA_CORTADA_CON_GUION.sub(r"\1\2", texto)


class _AcumuladorDeParrafos:
    """Agrupa líneas sueltas en párrafos, respetando líneas estructurales y vacías."""

    def __init__(self) -> None:
        self.lineas: list[str] = []
        self._parrafo_en_curso = ""

    def cerrar_parrafo(self) -> None:
        if self._parrafo_en_curso:
            self.lineas.append(self._parrafo_en_curso)
            self._parrafo_en_curso = ""

    def agregar_linea_independiente(self, linea: str) -> None:
        self.cerrar_parrafo()
        self.lineas.append(linea)

    def continuar_parrafo(self, linea: str) -> None:
        if self._parrafo_en_curso and not self._parrafo_en_curso.endswith(FINALES_DE_ORACION):
            self._parrafo_en_curso += " " + linea
            return
        self.cerrar_parrafo()
        self._parrafo_en_curso = linea


def unificar_parrafos(texto: str) -> str:
    """Regla 3b: une saltos de línea suaves, preservando listas legales, tablas y encabezados."""
    acumulador = _AcumuladorDeParrafos()
    for linea in texto.split("\n"):
        linea_limpia = linea.strip()
        if not linea_limpia or patrones.LINEA_ESTRUCTURAL.match(linea_limpia):
            acumulador.agregar_linea_independiente(linea_limpia)
        else:
            acumulador.continuar_parrafo(linea_limpia)
    acumulador.cerrar_parrafo()
    return "\n".join(acumulador.lineas)


def normalizar_terminos_legales(texto: str) -> str:
    """Regla 4: estandariza citas legales, agencias de crédito y cartas regulatorias."""
    for patron, forma_normalizada in TERMINOS_NORMALIZADOS:
        texto = patron.sub(forma_normalizada, texto)
    return texto


def _anonimizar_cuenta(coincidencia: re.Match[str]) -> str:
    tipo = coincidencia.group("tipo")
    simbolo = coincidencia.group("simbolo") or ""
    ultimos_digitos = coincidencia.group("ultimos_digitos")
    return f"{tipo} {simbolo}[REDACTED-{ultimos_digitos}]"


def anonimizar_pii(texto: str) -> str:
    """Regla 5: SSN -> [SSN-REDACTED-1775]; Acct# 1661310060 -> Acct #[REDACTED-0060]."""
    sin_ssn = patrones.SSN.sub(patrones.SSN_ANONIMIZADO, texto)
    return patrones.NUMERO_DE_CUENTA.sub(_anonimizar_cuenta, sin_ssn)
