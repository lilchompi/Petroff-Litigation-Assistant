"""Ingesta: limpia el JSONL de OCR con las 5 reglas, lo vectoriza y lo almacena."""

import json
import logging
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.limpieza import procesar_registro_ocr
from app.persistencia import almacen_documental
from app.persistencia.modelos import ChunkVectorial
from app.rag.chunking import dividir_en_chunks
from app.rag.embeddings import generador_embeddings

logger = logging.getLogger(__name__)

CODIFICACION_ENTRADA = "utf-8-sig"
CODIFICACION_SALIDA = "utf-8"


@dataclass
class ResultadoLimpieza:
    total_evaluados: int = 0
    documentos_limpios: list[dict[str, Any]] = field(default_factory=list)
    motivos_descarte: Counter[str] = field(default_factory=Counter)

    @property
    def total_descartados(self) -> int:
        return self.motivos_descarte.total()


def _leer_lineas_no_vacias(ruta: Path) -> Iterator[str]:
    with ruta.open(encoding=CODIFICACION_ENTRADA) as archivo:
        for linea in archivo:
            if linea.strip():
                yield linea


def limpiar_archivo(ruta: Path) -> ResultadoLimpieza:
    resultado = ResultadoLimpieza()
    for numero_linea, linea in enumerate(_leer_lineas_no_vacias(ruta), 1):
        resultado.total_evaluados += 1
        try:
            registro = json.loads(linea)
        except json.JSONDecodeError:
            logger.warning("Línea %d de %s no es JSON válido; se omite.", numero_linea, ruta)
            continue

        procesado = procesar_registro_ocr(registro)
        if procesado["se_descarta"]:
            resultado.motivos_descarte[procesado["motivo_descarte"]] += 1
        else:
            resultado.documentos_limpios.append(procesado)
    return resultado


def guardar_jsonl(documentos: list[dict[str, Any]], ruta: Path) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("w", encoding=CODIFICACION_SALIDA) as archivo:
        for documento in documentos:
            archivo.write(json.dumps(documento, ensure_ascii=False) + "\n")


def vectorizar_documento(documento: dict[str, Any]) -> list[ChunkVectorial]:
    textos = dividir_en_chunks(documento["texto_limpio"])
    embeddings = generador_embeddings.generar_lote(textos)
    metadata_documento = {
        "file_name": documento.get("file_name", ""),
        "caso": documento.get("caso", ""),
    }
    return [
        ChunkVectorial(
            indice=indice,
            texto=texto,
            embedding=embedding,
            metadata={"chars": len(texto), **metadata_documento},
        )
        for indice, (texto, embedding) in enumerate(zip(textos, embeddings, strict=True))
    ]


def indexar_documentos(documentos: list[dict[str, Any]]) -> int:
    """Vectoriza y guarda cada documento; devuelve el total de chunks creados."""
    total_chunks = 0
    for documento in documentos:
        chunks = vectorizar_documento(documento)
        almacen_documental.guardar_documento_y_chunks(documento, chunks)
        total_chunks += len(chunks)
    return total_chunks


def ejecutar_ingesta(ruta_entrada: Path) -> dict[str, Any]:
    """Limpia, guarda el JSONL limpio, indexa y devuelve las métricas del proceso.

    Lanza FileNotFoundError si `ruta_entrada` no existe.
    """
    if not ruta_entrada.exists():
        raise FileNotFoundError(f"No existe el archivo {ruta_entrada}")

    limpieza = limpiar_archivo(ruta_entrada)
    guardar_jsonl(limpieza.documentos_limpios, settings.OUTPUT_CLEAN_JSONL)
    total_chunks = indexar_documentos(limpieza.documentos_limpios)

    return {
        "archivo_procesado": str(ruta_entrada),
        "archivo_limpio_generado": str(settings.OUTPUT_CLEAN_JSONL),
        "total_registros_evaluados": limpieza.total_evaluados,
        "documentos_descartados_regla_1": limpieza.total_descartados,
        "documentos_limpios_guardados": len(limpieza.documentos_limpios),
        "total_chunks_vectorizados_pgvector": total_chunks,
        "desglose_motivos_descarte": dict(limpieza.motivos_descarte),
        "base_de_datos": almacen_documental.descripcion_motor,
    }
