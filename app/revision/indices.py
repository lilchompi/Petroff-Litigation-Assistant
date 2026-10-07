"""Los index de corte que aparecen en el texto de un documento, sin el ruido.

Solo cuentan los de la carátula (el principio del documento, donde va la caption): un index
que solo aparece en el cuerpo suele ser una referencia (una acción previa, un cónyuge).
"""

import re

from app.revision.nombres import index_federal

# La carátula de una radicación de NYSCEF cabe holgadamente en esto.
CARACTERES_CARATULA = 2500
ANIO_MINIMO, ANIO_MAXIMO = 1900, 2099
DIGITOS_ANIO = 4

# NNNNNN/AAAA, como lo imprime la corte. Con guion solo si va precedido de "Index", porque
# 'NNNNNN-AAAA' suelto se confunde con cuentas y teléfonos.
INDEX_CON_BARRA = re.compile(r"(?<![\d/])(\d{3,7})\s?/\s?((?:19|20)\d{2})(?![\d/])")
INDEX_CON_GUION = re.compile(
    r"index\s*(?:no\.?|number|#)?\s*[:.]?\s*(\d{3,7})\s?-\s?((?:19|20)\d{2})(?!\d)",
    re.IGNORECASE,
)
INDEX_FEDERAL = re.compile(r"(?<!\d)(\d):(\d{2})-cv-(\d{3,5})(?!\d)", re.IGNORECASE)


def _es_rango_de_anios(numero: str) -> bool:
    """'2019/2020' es un periodo, no un index."""
    return len(numero) == DIGITOS_ANIO and ANIO_MINIMO <= int(numero) <= ANIO_MAXIMO


def indices_en(texto: str) -> set[str]:
    encontrados = {
        f"{int(n)}/{a}"
        for patron in (INDEX_CON_BARRA, INDEX_CON_GUION)
        for n, a in patron.findall(texto)
        if not _es_rango_de_anios(n)
    }
    return encontrados | {index_federal(*grupos) for grupos in INDEX_FEDERAL.findall(texto)}


def indices_de_caratula(texto: str | None) -> frozenset[str]:
    return frozenset(indices_en(texto[:CARACTERES_CARATULA])) if texto else frozenset()


def es_fragmento_de(candidato: str, propio: str | None) -> bool:
    """'593/2026' dentro de '501593/2026': el OCR partió el index propio."""
    if not propio or candidato == propio or "/" not in candidato or "/" not in propio:
        return False
    numero, anio = candidato.split("/")
    numero_propio, anio_propio = propio.split("/")
    return anio == anio_propio and numero_propio.endswith(numero)
