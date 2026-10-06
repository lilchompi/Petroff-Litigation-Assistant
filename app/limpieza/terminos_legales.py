"""Catálogo de términos legales críticos y su forma normalizada (Regla 4)."""

import re

_TERMINOS_FORECLOSURE_NY = [
    (
        r"\bRPAPL\s*§?\s*1304\b|\b90[\s-]day\s+pre[\s-]foreclosure\s+notice\b",
        "RPAPL § 1304 (90-Day Pre-Foreclosure Notice)",
    ),
    (
        r"\bCPLR\s*§?\s*3408\b|\bmandatory\s+settlement\s+conference\b",
        "CPLR § 3408 (Mandatory Settlement Conference)",
    ),
    (
        r"\bFAPA\b|\bForeclosure\s+Abuse\s+Prevention\s+Act\b",
        "FAPA (Foreclosure Abuse Prevention Act, CPLR 203/213)",
    ),
    (r"\ballong[es]?\b", "Allonge"),
    (r"\bpromiss?ory\s+note\b|\bmortgage\s+note\b", "Promissory Note"),
    (r"\bmortgagee\b", "Mortgagee"),
    (r"\bmortgagor\b", "Mortgagor"),
    (r"\bnotice\s+of\s+pendency\b|\blis\s+pendens\b", "Notice of Pendency (Lis Pendens)"),
]

_TERMINOS_FCRA = [
    (r"\btrans[\s-]?union\b", "TransUnion"),
    (r"\bexperian\b", "Experian"),
    (r"\bequifax\b", "Equifax"),
    (r"\binnovis\b", "Innovis"),
    (
        r"\bconsumer\s+reporting\s+agenc(?:y|ies)\b|\bCRA\b",
        "Consumer Reporting Agency (CRA)",
    ),
    (r"\bfurnisher\s+of\s+information\b|\bfurnisher\b", "Furnisher of Information"),
    (r"\bmetro\s*2\b", "Metro 2"),
]

_TERMINOS_RESPA_TILA_FDCPA = [
    (r"\bqualified\s+written\s+request\b|\bQWR\b", "Qualified Written Request (QWR)"),
    (r"\bnotice\s+of\s+error\b|\bNOE\b", "Notice of Error (NOE)"),
    (
        r"\brequest\s+for\s+information\b|\bRFI\b",
        "Request for Information (RFI) bajo Reg X (12 CFR § 1024)",
    ),
    (
        r"\bdebt\s+validation\s+(?:letter|notice)\b",
        "Debt Validation Letter bajo FDCPA § 1692g",
    ),
]

TERMINOS_NORMALIZADOS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(patron, re.IGNORECASE), forma_normalizada)
    for patron, forma_normalizada in (
        _TERMINOS_FORECLOSURE_NY + _TERMINOS_FCRA + _TERMINOS_RESPA_TILA_FDCPA
    )
]
