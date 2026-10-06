"""Ejecuta la limpieza de las 5 reglas sobre el JSONL de entrada, lo indexa y prueba una consulta.

Uso: python -m scripts.ejecutar_limpieza
"""

from typing import Any

from app.core.config import settings
from app.core.constantes import PORCENTAJE
from app.servicios.consulta import servicio_consulta
from app.servicios.ingesta import ejecutar_ingesta
from scripts.consola import imprimir_seccion, imprimir_separador, imprimir_titulo

PREGUNTA_DE_PRUEBA = (
    "¿Qué orden dictó la corte en el caso Morris y qué requerimientos impuso al banco M&T?"
)
CASO_DE_PRUEBA = "Morris"
TOP_K_DE_PRUEBA = 3

DESCRIPCION_REGLAS = [
    "Regla 1: Filtro de Descarte (< 45% conf, < 25 chars, > 40% símbolos)",
    "Regla 2: Eliminación de Artefactos PaddleOCR y Unicode roto",
    "Regla 3: Des-guionado (De-hyphenation) y Unificación de Párrafos",
    "Regla 4: Normalización de Términos Legales (RPAPL, CPLR, FAPA, QWR, FCRA)",
    "Regla 5: Anonimización de PII ([SSN-REDACTED-XXXX], [REDACTED-XXXX])",
]


def imprimir_metricas(metricas: dict[str, Any]) -> None:
    imprimir_seccion("RESULTADOS DE LIMPIEZA E INGESTA:")
    print(f"  • Total registros evaluados       : {metricas['total_registros_evaluados']}")
    print(f"  • Documentos descartados (Regla 1): {metricas['documentos_descartados_regla_1']}")
    print(f"  • Documentos limpios aprobados    : {metricas['documentos_limpios_guardados']}")
    print(f"  • Chunks vectorizados creados     : {metricas['total_chunks_vectorizados_pgvector']}")
    print(f"  • Motor de almacenamiento BD      : {metricas['base_de_datos']}")
    print(f"  • Archivo limpio guardado en      : {metricas['archivo_limpio_generado']}")

    if metricas["desglose_motivos_descarte"]:
        print("\n  Desglose de motivos de descarte:")
        for motivo, cantidad in metricas["desglose_motivos_descarte"].items():
            print(f"    - {motivo}: {cantidad} doc(s)")


def imprimir_dictamen(dictamen: dict[str, Any]) -> None:
    print(f"  Fuentes encontradas: {len(dictamen['fuentes'])}")
    for fuente in dictamen["fuentes"]:
        similitud = fuente["similitud"] * PORCENTAJE
        print(f"    * {fuente['archivo']} ({fuente['caso']}) - Similitud: {similitud:.1f}%")

    print("\n  Respuesta del Agente:")
    imprimir_separador()
    print(dictamen["respuesta"])
    imprimir_separador()


def main() -> None:
    imprimir_titulo("PETROFF AMSHEN LLP - PIPELINE DE LIMPIEZA OCR & RAG VECTORIAL")

    ruta_entrada = settings.INPUT_JSONL
    print(f"\n[1] Archivo origen: {ruta_entrada}")
    if not ruta_entrada.exists():
        print(f"Error: no se encuentra {ruta_entrada}")
        return

    print("\n[2] Aplicando las 5 Reglas de Limpieza y Normalización:")
    for descripcion in DESCRIPCION_REGLAS:
        print(f"    - {descripcion}")
    imprimir_metricas(ejecutar_ingesta(ruta_entrada))

    imprimir_titulo("[3] PRUEBA DE CONSULTA AL AGENTE CLAUDE (RETRIEVAL SEMÁNTICO)")
    print(f"  Pregunta: {PREGUNTA_DE_PRUEBA}\n")
    imprimir_dictamen(
        servicio_consulta.consultar_caso(
            pregunta=PREGUNTA_DE_PRUEBA, caso=CASO_DE_PRUEBA, top_k=TOP_K_DE_PRUEBA
        )
    )


if __name__ == "__main__":
    main()
