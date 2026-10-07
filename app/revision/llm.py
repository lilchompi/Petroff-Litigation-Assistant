"""Capa 2: el LLM decide los hallazgos ambiguos de la revisión, con el OCR ya limpio.

Al LLM solo le llega el texto DESPUÉS de pasar por la limpieza del repo (reglas 2 a 5), es
decir, con SSN, cuentas, teléfonos, correos y fechas de nacimiento enmascarados, y solo el
principio de cada documento (la carátula). No decide nada en SharePoint: su respuesta queda
como recomendación con motivo y evidencia, y una persona la aprueba. El campo
`regla_sugerida` es lo que usará la capa 3 para proponer cambios a las reglas.
"""

import json
from dataclasses import dataclass, field
from typing import Any

import anthropic

from app.core.config import settings
from app.limpieza import procesar_registro_ocr
from app.revision.plan import Hallazgo

CARACTERES_POR_DOCUMENTO = 2500
DOCUMENTOS_POR_HALLAZGO = 3
MAX_TOKENS = 4000
BETA_FALLBACK = "server-side-fallback-2026-07-01"

DECISIONES = [
    "mover_a_otra_carpeta",
    "relacion_entre_casos",
    "plantilla_con_index_equivocado",
    "fusionar_carpetas",
    "separar_casos_en_subcarpetas",
    "renombrar_con_otro_index",
    "ruido_ignorar",
    "no_se_puede_decidir",
]
ESQUEMA = {
    "type": "object",
    "properties": {
        "decision": {"type": "string", "enum": DECISIONES},
        "carpeta_destino": {"type": "string"},
        "confianza": {"type": "string", "enum": ["alta", "media", "baja"]},
        "motivo": {"type": "string"},
        "evidencia": {"type": "string"},
        "regla_sugerida": {"type": "string"},
    },
    "required": [
        "decision",
        "carpeta_destino",
        "confianza",
        "motivo",
        "evidencia",
        "regla_sugerida",
    ],
    "additionalProperties": False,
}

SISTEMA = """Eres un paralegal senior de Petroff Amshen LLP (Nueva York). Revisas la calidad de
las carpetas de casos (matters) en SharePoint. Cada carpeta se llama
'Cliente - <ID interno> - <index>'. El primer dígito del ID es el tipo de caso:
1 Time-Barred Debt, 2 Article 15, 4 ID Theft + WF Reporting, 5 Chapter 7/13,
6 Foreclosure y Appeal, 7 RESPA, 8 Identity Theft, 9 Wrongful Reporting.

Reglas firmes de la firma:
- El index (número de la corte, p. ej. 826173/2025 o 1:23-cv-01270) es lo ÚNICO que identifica
  un caso. El nombre del cliente no: hay clientes con varios casos, cónyuges con el mismo
  apellido y personas que se cambiaron el nombre.
- Un documento está mal archivado solo si es un documento COMPLETO (moción, orden,
  estipulación) cuya propia carátula e index son de otro caso. Citar otro index en el cuerpo
  (una acción previa sobre la misma propiedad, un cónyuge, una apelación) NO es un error.
- Un Article 15 cita siempre el foreclosure que quiere cancelar. Una bancarrota cita las
  anteriores. Eso es relación entre casos, no un error.
- Un número de apelación tiene el año primero (2025-09763) y no es el index de primera
  instancia.
- Ante la duda, 'no_se_puede_decidir'. Un documento mal archivado se pierde; uno sin archivar
  solo molesta.

El texto viene del OCR, ya limpio y con los datos personales enmascarados ([SSN-REDACTED-…],
[REDACTED-…], [TEL-REDACTED-…], [EMAIL-REDACTED], [DOB-REDACTED]). Solo ves el principio de
cada documento. Responde con la decisión, la carpeta destino si aplica (nombre exacto de una
de las carpetas que se te dan, o vacío), tu confianza, el motivo en una o dos frases, la
evidencia (una cita breve del texto) y, si ves un patrón que una regla automática podría
resolver sin ti, descríbelo en regla_sugerida (o déjalo vacío)."""


@dataclass
class Consulta:
    hallazgo: Hallazgo
    carpetas: list[str]
    documentos: list[dict[str, str]]

    def mensaje(self) -> str:
        return json.dumps(
            {
                "hallazgo": {"regla": self.hallazgo.regla, "descripcion": self.hallazgo.headline},
                "carpeta_revisada": self.hallazgo.carpeta,
                "carpetas_relacionadas": self.carpetas,
                "documentos": self.documentos,
            },
            ensure_ascii=False,
            indent=1,
        )


@dataclass
class Respuesta:
    consulta: Consulta
    decision: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    tokens_entrada: int = 0
    tokens_salida: int = 0
    modelo: str = ""

    def a_dict(self) -> dict[str, Any]:
        h = self.consulta.hallazgo
        return {
            "carpeta": h.carpeta,
            "regla": h.regla,
            "headline": h.headline,
            "documentos": [d["archivo"] for d in self.consulta.documentos],
            "modelo": self.modelo,
            "tokens_entrada": self.tokens_entrada,
            "tokens_salida": self.tokens_salida,
            "error": self.error,
            **self.decision,
        }


def texto_limpio(registro: dict[str, Any]) -> str | None:
    """El texto del documento tras las 5 reglas de limpieza, recortado a la carátula."""
    procesado = procesar_registro_ocr(registro)
    if procesado["se_descarta"] or not procesado["texto_limpio"]:
        return None
    return procesado["texto_limpio"][:CARACTERES_POR_DOCUMENTO]


def armar_consulta(
    hallazgo: Hallazgo, registros: list[dict[str, Any]], carpetas: list[str]
) -> Consulta:
    """Elige los documentos que justifican el hallazgo y deja solo su texto limpio."""
    nombres = set(hallazgo.datos.get("documentos") or [])
    if hallazgo.datos.get("file_name"):
        nombres.add(hallazgo.datos["file_name"])
    elegidos = [r for r in registros if r.get("file_name") in nombres] or registros
    documentos = []
    for registro in elegidos:
        texto = texto_limpio(registro)
        if texto:
            documentos.append(
                {
                    "archivo": registro.get("file_name", ""),
                    "subcarpeta": str(registro.get("origen") or registro.get("subfolder") or ""),
                    "texto": texto,
                }
            )
        if len(documentos) >= DOCUMENTOS_POR_HALLAZGO:
            break
    return Consulta(hallazgo, carpetas, documentos)


class ClasificadorLLM:
    def __init__(
        self, cliente: anthropic.Anthropic | None = None, modelo: str | None = None
    ) -> None:
        self.cliente = cliente or anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY or None)
        self.modelo = modelo or settings.CLAUDE_MODEL_REVISION

    def decidir(self, consulta: Consulta) -> Respuesta:
        respuesta = Respuesta(consulta, modelo=self.modelo)
        if not consulta.documentos:
            respuesta.error = "sin texto utilizable (OCR vacío o descartado por la limpieza)"
            return respuesta
        try:
            mensaje = self.cliente.beta.messages.create(
                model=self.modelo,
                max_tokens=MAX_TOKENS,
                betas=[BETA_FALLBACK],
                fallbacks="default",
                system=SISTEMA,
                output_config={
                    "effort": "medium",
                    "format": {"type": "json_schema", "schema": ESQUEMA},
                },
                messages=[{"role": "user", "content": consulta.mensaje()}],
            )
        except anthropic.APIError as error:
            respuesta.error = f"{type(error).__name__}: {error}"[:300]
            return respuesta
        respuesta.tokens_entrada = mensaje.usage.input_tokens
        respuesta.tokens_salida = mensaje.usage.output_tokens
        respuesta.modelo = mensaje.model
        if mensaje.stop_reason == "refusal":
            respuesta.error = "el modelo declinó la consulta (refusal)"
            return respuesta
        texto = next((b.text for b in mensaje.content if b.type == "text"), "")
        try:
            respuesta.decision = json.loads(texto)
        except json.JSONDecodeError:
            respuesta.error = f"respuesta no es JSON (stop_reason: {mensaje.stop_reason})"
        return respuesta
