"""Estructuras de datos y mapeo a filas compartidos por los repositorios."""

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

CONFIANZA_POR_DEFECTO = 100.0
TAMANO_MB_POR_DEFECTO = 0.0


class Tabla(StrEnum):
    DOCUMENTOS = "documentos_legales"
    CHUNKS = "chunks_vectoriales"


COLUMNAS_DOCUMENTO = (
    "id",
    "caso",
    "file_name",
    "subfolder",
    "size_mb",
    "origen",
    "document_type",
    "contains_ssn",
    "confianza_promedio",
    "total_caracteres",
    "texto_limpio",
    "metadata",
)

COLUMNAS_CHUNK = (
    "doc_id",
    "caso",
    "file_name",
    "subfolder",
    "chunk_index",
    "chunk_text",
    "embedding",
    "metadata",
)


@dataclass(frozen=True)
class ChunkVectorial:
    indice: int
    texto: str
    embedding: list[float]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FragmentoRecuperado:
    doc_id: str
    caso: str
    file_name: str
    subfolder: str | None
    chunk_index: int
    chunk_text: str
    similitud: float


def sql_insercion(tabla: Tabla, columnas: tuple[str, ...], marcador: str) -> str:
    marcadores = ", ".join([marcador] * len(columnas))
    return f"INSERT INTO {tabla} ({', '.join(columnas)}) VALUES ({marcadores})"


def valores_documento(documento: dict[str, Any]) -> tuple[Any, ...]:
    texto_limpio = documento.get("texto_limpio", "")
    return (
        documento["id"],
        documento.get("caso", ""),
        documento.get("file_name", ""),
        documento.get("subfolder", ""),
        documento.get("size_mb", TAMANO_MB_POR_DEFECTO),
        documento.get("origen", ""),
        documento.get("document_type"),
        bool(documento.get("contains_ssn")),
        documento.get("confianza_promedio", CONFIANZA_POR_DEFECTO),
        len(texto_limpio),
        texto_limpio,
        json.dumps(documento.get("metadata", {})),
    )


def valores_chunk(
    documento: dict[str, Any],
    chunk: ChunkVectorial,
    serializar_embedding: Callable[[list[float]], Any],
) -> tuple[Any, ...]:
    return (
        documento["id"],
        documento.get("caso", ""),
        documento.get("file_name", ""),
        documento.get("subfolder", ""),
        chunk.indice,
        chunk.texto,
        serializar_embedding(chunk.embedding),
        json.dumps(chunk.metadata),
    )
