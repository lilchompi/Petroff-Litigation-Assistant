"""Script de Benchmark Completo End-to-End para Petroff Amshen LLP.

Mide con precisión milimétrica cada fase del flujo:
1. Limpieza de 5 reglas sobre todo el archivo JSONL.
2. Fragmentación y generación de embeddings locales.
3. Indexación y almacenamiento en la base de datos.
4. Retrieval semántico vectorial de la pregunta.
5. Inferencia y redacción jurídica del LLM (Claude Sonnet 5.5).
"""

from __future__ import annotations

import sys
import time
import json
from pathlib import Path
from typing import Dict, Any

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from app.core.config import settings
from app.servicios.ingesta import ejecutar_ingesta
from app.servicios.consulta import servicio_consulta
from app.rag.embeddings import generador_embeddings
from app.persistencia import almacen_documental


def formatear_tiempo(segundos: float) -> str:
    if segundos < 1.0:
        return f"{segundos * 1000:.1f} ms"
    return f"{segundos:.2f} s"


def ejecutar_benchmark_completo():
    print("\n" + "=" * 78)
    print("      BENCHMARK END-TO-END: PIPELINE COMPLETO OCR + RAG + CLAUDE LLM")
    print("      PETROFF AMSHEN LLP - FORECLOSURE DEFENSE")
    print("=" * 78)

    ruta_entrada = settings.INPUT_JSONL
    
    # Base de datos aislada para benchmark para medir insercion limpia sin bloqueos de visores
    ruta_benchmark_db = settings.SQLITE_PATH.parent / "vector_store_benchmark.db"
    if ruta_benchmark_db.exists():
        try:
            ruta_benchmark_db.unlink()
        except Exception:
            pass
    from app.persistencia.repositorio_sqlite import RepositorioSqlite
    almacen_documental.sqlite = RepositorioSqlite(ruta_benchmark_db)

    print(f"\n[ARCHIVO] Archivo a procesar : {ruta_entrada}")
    print(f"[MODELO]  Modelo LLM activo  : {settings.CLAUDE_MODEL}")
    print(f"[VECTORES] Modelo Embeddings : {settings.EMBEDDING_MODEL_NAME} ({settings.EMBEDDING_DIM}d)")
    print(f"[MOTOR]   Almacen Documental : {almacen_documental.descripcion_motor} ({ruta_benchmark_db.name})\n")

    t_inicio_total = time.perf_counter()

    # -------------------------------------------------------------------------
    # FASE 1, 2 y 3: INGESTA COMPLETA (Limpieza + Embeddings + Base de Datos)
    # -------------------------------------------------------------------------
    print("-" * 78)
    print(" [FASE 1 A 3] EJECUTANDO LIMPIEZA DE 5 REGLAS, EMBEDDINGS E INDEXACIÓN")
    print("-" * 78)

    t0_ingesta = time.perf_counter()
    metricas_ingesta = ejecutar_ingesta(ruta_entrada)
    t_ingesta = time.perf_counter() - t0_ingesta

    total_docs = metricas_ingesta["total_registros_evaluados"]
    docs_limpios = metricas_ingesta["documentos_limpios_guardados"]
    total_chunks = metricas_ingesta["total_chunks_vectorizados_pgvector"]

    print(f"  [OK] Documentos evaluados con 5 Reglas : {total_docs}")
    print(f"  [OK] Documentos limpios aprobados       : {docs_limpios}")
    print(f"  [OK] Chunks vectorizados e indexados   : {total_chunks}")
    print(f"  [TIEMPO] Ingesta Total (Fase 1 a 3)    : {formatear_tiempo(t_ingesta)}")
    print(f"  [VELOCIDAD] Rendimiento Ingesta        : {total_docs / max(t_ingesta, 0.001):.1f} docs/segundo")

    # -------------------------------------------------------------------------
    # FASE 4: RETRIEVAL VECTORIAL SEMÁNTICO
    # -------------------------------------------------------------------------
    pregunta = "¿Qué orden dictó la corte en el caso Morris y qué requerimientos impuso al banco M&T?"
    caso = "Morris"
    top_k = 3

    print("\n" + "-" * 78)
    print(" [FASE 4] RETRIEVAL VECTORIAL SEMANTICO (BUSQUEDA)")
    print("-" * 78)
    print(f"  Consulta: \"{pregunta}\"")
    print(f"  Filtro caso: \"{caso}\" (top_k={top_k})")

    t0_vectorizar = time.perf_counter()
    emb_query = generador_embeddings.generar(pregunta)
    t_vectorizar = time.perf_counter() - t0_vectorizar

    t0_busqueda = time.perf_counter()
    fragmentos = almacen_documental.busqueda_vectorial(emb_query, caso=caso, top_k=top_k)
    t_busqueda = time.perf_counter() - t0_busqueda
    t_retrieval_total = t_vectorizar + t_busqueda

    print(f"  [TIEMPO] Vectorizacion de la pregunta  : {formatear_tiempo(t_vectorizar)}")
    print(f"  [TIEMPO] Busqueda coseno en BD         : {formatear_tiempo(t_busqueda)}")
    print(f"  [TIEMPO] Subtotal Retrieval            : {formatear_tiempo(t_retrieval_total)}")
    print(f"  [OK] Fuentes documentales recuperadas  : {len(fragmentos)}")
    for f in fragmentos:
        print(f"     * {f.file_name} ({f.caso}) -> Similitud: {f.similitud * 100:.1f}%")

    # -------------------------------------------------------------------------
    # FASE 5: INFERENCIA Y RESPUESTA DEL LLM (CLAUDE)
    # -------------------------------------------------------------------------
    print("\n" + "-" * 78)
    print(f" [FASE 5] INFERENCIA DEL LLM ({settings.CLAUDE_MODEL})")
    print("-" * 78)
    print("  Enviando contexto documental estructurado a la API de Anthropic...")

    t0_llm = time.perf_counter()
    dictamen = servicio_consulta.consultar_caso(pregunta=pregunta, caso=caso, top_k=top_k)
    t_llm = time.perf_counter() - t0_llm

    longitud_respuesta = len(dictamen["respuesta"])
    palabras_respuesta = len(dictamen["respuesta"].split())
    estimacion_tokens = int(palabras_respuesta * 1.3)

    print(f"  [TIEMPO] Respuesta de Claude LLM       : {formatear_tiempo(t_llm)}")
    print(f"  [TAMANO] Tamano de la respuesta        : {longitud_respuesta} caracteres (~{palabras_respuesta} palabras)")
    print(f"  [VELOCIDAD] Velocidad de generacion    : {estimacion_tokens / max(t_llm, 0.001):.1f} tokens/segundo")

    t_total_proceso = time.perf_counter() - t_inicio_total

    # -------------------------------------------------------------------------
    # RESPUESTA GENERADA
    # -------------------------------------------------------------------------
    print("\n" + "=" * 78)
    print("  RESPUESTA DEL AGENTE JURÍDICO (TEXTO LIMPIO):")
    print("=" * 78)
    print(dictamen["respuesta"])

    # -------------------------------------------------------------------------
    # CUADRO RESUMEN DE TIEMPOS Y LATENCIAS
    # -------------------------------------------------------------------------
    print("\n" + "=" * 78)
    print("  RESUMEN EJECUTIVO DE TIEMPOS (PROCESAMIENTO END-TO-END)")
    print("=" * 78)
    print(f"  {'FASE':<45} | {'TIEMPO':<12} | {'% TOTAL'}")
    print("  " + "-" * 74)
    pct_ingesta = (t_ingesta / t_total_proceso) * 100
    pct_retrieval = (t_retrieval_total / t_total_proceso) * 100
    pct_llm = (t_llm / t_total_proceso) * 100

    print(f"  {'1. Limpieza OCR 5 Reglas + Embeddings + BD':<45} | {formatear_tiempo(t_ingesta):<12} | {pct_ingesta:5.1f}%")
    print(f"  {'2. Retrieval Vectorial (Pregunta + Similitud)':<45} | {formatear_tiempo(t_retrieval_total):<12} | {pct_retrieval:5.1f}%")
    print(f"  {'3. Inferencia LLM (Claude Sonnet 5.5)':<45} | {formatear_tiempo(t_llm):<12} | {pct_llm:5.1f}%")
    print("  " + "-" * 74)
    print(f"  {'TIEMPO TOTAL DEL FLUJO COMPLETO':<45} | {formatear_tiempo(t_total_proceso):<12} | 100.0%")
    print("=" * 78 + "\n")


if __name__ == "__main__":
    ejecutar_benchmark_completo()
