"""Lógica de escritura común a los repositorios SQL."""

from abc import ABC, abstractmethod
from collections.abc import Iterator
from contextlib import AbstractContextManager
from typing import Any

from app.persistencia.modelos import (
    COLUMNAS_CHUNK,
    ChunkVectorial,
    Tabla,
    sql_insercion,
    valores_chunk,
    valores_documento,
)


class RepositorioSqlBase(ABC):
    MARCADOR_PARAMETRO: str
    SQL_UPSERT_DOCUMENTO: str

    @abstractmethod
    def _cursor(self) -> AbstractContextManager[Any]:
        """Cursor dentro de una transacción que se confirma al salir sin errores."""

    @abstractmethod
    def _serializar_embedding(self, embedding: list[float]) -> Any: ...

    def guardar_documento_y_chunks(
        self, documento: dict[str, Any], chunks: list[ChunkVectorial]
    ) -> None:
        """Inserta o reemplaza el documento y sustituye por completo sus chunks."""
        marcador = self.MARCADOR_PARAMETRO
        with self._cursor() as cursor:
            cursor.execute(self.SQL_UPSERT_DOCUMENTO, valores_documento(documento))
            cursor.execute(
                f"DELETE FROM {Tabla.CHUNKS} WHERE doc_id = {marcador}", (documento["id"],)
            )
            cursor.executemany(
                sql_insercion(Tabla.CHUNKS, COLUMNAS_CHUNK, marcador),
                self._filas_de_chunks(documento, chunks),
            )

    def _filas_de_chunks(
        self, documento: dict[str, Any], chunks: list[ChunkVectorial]
    ) -> Iterator[tuple[Any, ...]]:
        for chunk in chunks:
            yield valores_chunk(documento, chunk, self._serializar_embedding)

    def contar_registros(self, tabla: Tabla) -> int:
        with self._cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) AS total FROM {tabla}")
            return cursor.fetchone()["total"]
