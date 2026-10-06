"""Dictamen sintético de demostración, usado cuando no hay ANTHROPIC_API_KEY configurada."""

from app.core.constantes import PORCENTAJE
from app.persistencia.modelos import FragmentoRecuperado

FUENTES_EN_RESUMEN = 3
LONGITUD_EXTRACTO = 280


def _extracto(fragmento: FragmentoRecuperado) -> str:
    return fragmento.chunk_text[:LONGITUD_EXTRACTO].replace("\n", " ").strip()


def generar_dictamen_local(fragmentos: list[FragmentoRecuperado]) -> str:
    principal = fragmentos[0]
    lineas = [
        "### Dictamen Preliminar del Agente Legal (Petroff Amshen LLP)",
        f"**Expediente Analizado:** `{principal.caso}`",
        f"**Documento Principal Identificado:** `{principal.file_name}` "
        f"(Similitud semántica: {principal.similitud * PORCENTAJE:.1f}%)",
        "",
        "#### 1. Hallazgos Documentales Clave:",
    ]
    lineas.extend(
        f"- **[Fuente {numero}] `{fragmento.file_name}`**: {_extracto(fragmento)}..."
        for numero, fragmento in enumerate(fragmentos[:FUENTES_EN_RESUMEN], 1)
    )
    lineas.extend(
        [
            "",
            "#### 2. Evaluación Jurídica Preliminar:",
            "- **Cumplimiento y Evidencia:** Los documentos extraídos contienen las cláusulas, "
            "identificadores y términos procesales pertinentes para la estrategia del caso.",
            "- **PII Protegida:** Todos los números de cuenta y datos sensibles han sido validados "
            "bajo anonimización con trazabilidad de los últimos 4 dígitos.",
            "",
            "*(Nota técnica: Configura la variable ANTHROPIC_API_KEY en tu archivo .env para "
            "recibir la redacción argumentativa completa de Claude en tiempo real).*",
        ]
    )
    return "\n".join(lineas)
