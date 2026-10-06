"""Expresiones regulares precompiladas usadas por las reglas de limpieza."""

import re

CARACTERES_ASIATICOS = re.compile(r"[一-鿿]+")
CARACTERES_CONTROL_Y_UNICODE_ROTO = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f�]")
LINEA_DE_RELLENO = re.compile(r"^[#*_\-=\s]{3,}$", re.MULTILINE)

PALABRA_CORTADA_CON_GUION = re.compile(r"(\b[a-zA-Z]+)-\s*\n\s*([a-zA-Z]+\b)")

LINEA_ESTRUCTURAL = re.compile(
    r"^(\d+\.|\([a-zA-Z0-9]+\)|Section\b|Article\b|ORDERED\b|WHEREAS\b|EXHIBIT\b|•|\*|-|\||#)\s*",
    re.IGNORECASE,
)

SIMBOLO_NO_ALFANUMERICO = re.compile(r"[^a-zA-Z0-9\s]")

SSN = re.compile(r"\b(\d{3})[- ]?(\d{2})[- ]?(\d{4})\b")
SSN_ANONIMIZADO = r"[SSN-REDACTED-\3]"

NUMERO_DE_CUENTA = re.compile(
    r"\b(?P<tipo>Acct|Account|Loan|Claim|Policy)\s*(?P<simbolo>#|Number|No\.?)?[\s:]*"
    r"[A-Za-z0-9*]{2,16}(?P<ultimos_digitos>[A-Za-z0-9]{4})\b",
    re.IGNORECASE,
)

MARCA_PII_ANONIMIZADA = re.compile(r"\[(SSN|REDACTED)")

SALTOS_DE_LINEA_EXCESIVOS = re.compile(r"\n{3,}")
SEPARADOR_DE_PARRAFO = "\n\n"

CONFIANZA_EN_DESCRIPCION_OCR = re.compile(r"confidence\s+([\d.]+)")
