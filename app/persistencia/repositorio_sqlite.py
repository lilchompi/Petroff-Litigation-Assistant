"""Almacén vectorial local en SQLite; la similitud coseno se calcula en Python."""

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from app.persistencia.modelos import (
    COLUMNAS_DOCUMENTO,
    FragmentoRecuperado,
    Tabla,
    sql_insercion,
)
from app.persistencia.repositorio_base import RepositorioSqlBase

DECIMALES_SIMILITUD = 4

SQL_ESQUEMA = f"""
CREATE TABLE IF NOT EXISTS {Tabla.DOCUMENTOS} (
    id TEXT PRIMARY KEY,
    caso TEXT,
    file_name TEXT,
    subfolder TEXT,
    size_mb REAL,
    origen TEXT,
    document_type TEXT,
    contains_ssn INTEGER,
    confianza_promedio REAL,
    total_caracteres INTEGER,
    texto_limpio TEXT,
    metadata TEXT
);

CREATE TABLE IF NOT EXISTS {Tabla.CHUNKS} (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id TEXT,
    caso TEXT,
    file_name TEXT,
    subfolder TEXT,
    chunk_index INTEGER,
    chunk_text TEXT,
    embedding TEXT,
    metadata TEXT
);
"""


def _similitud_coseno(vector_a: list[float], vector_b: list[float]) -> float:
    """Producto punto; equivale al coseno porque ambos vectores están normalizados (L2)."""
    return sum(a * b for a, b in zip(vector_a, vector_b, strict=False))


class RepositorioSqlite(RepositorioSqlBase):
    MARCADOR_PARAMETRO = "?"
    SQL_UPSERT_DOCUMENTO = sql_insercion(Tabla.DOCUMENTOS, COLUMNAS_DOCUMENTO, "?").replace(
        "INSERT", "INSERT OR REPLACE", 1
    )

    def __init__(self, ruta: Path) -> None:
        self.ruta = ruta
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        self._conexion = sqlite3.connect(self.ruta, timeout=60.0, check_same_thread=False)
        self._conexion.row_factory = sqlite3.Row
        self._conexion.execute("PRAGMA busy_timeout = 60000;")
        self._conexion.executescript(SQL_ESQUEMA)
        self._conexion.commit()

    @contextmanager
    def _cursor(self) -> Iterator[sqlite3.Cursor]:
        with self._conexion:
            yield self._conexion.cursor()

    def _serializar_embedding(self, embedding: list[float]) -> str:
        return json.dumps(embedding)

    def busqueda_vectorial(
        self, embedding_consulta: list[float], caso: str | None, top_k: int
    ) -> list[FragmentoRecuperado]:
        consulta = (
            "SELECT doc_id, caso, file_name, subfolder, chunk_index, chunk_text, embedding "
            f"FROM {Tabla.CHUNKS}"
        )
        parametros: list[str] = []
        if caso:
            consulta += " WHERE caso LIKE ?"
            parametros.append(f"%{caso}%")

        with self._cursor() as cursor:
            cursor.execute(consulta, parametros)
            filas = cursor.fetchall()

        fragmentos = [self._fragmento_desde_fila(fila, embedding_consulta) for fila in filas]
        fragmentos.sort(key=lambda fragmento: fragmento.similitud, reverse=True)
        return fragmentos[:top_k]

    @staticmethod
    def _fragmento_desde_fila(
        fila: sqlite3.Row, embedding_consulta: list[float]
    ) -> FragmentoRecuperado:
        *columnas, embedding_serializado = fila
        similitud = _similitud_coseno(embedding_consulta, json.loads(embedding_serializado))
        return FragmentoRecuperado(*columnas, similitud=round(similitud, DECIMALES_SIMILITUD))

    def listar_casos(self) -> list[dict[str, Any]]:
        with self._cursor() as cursor:
            cursor.execute(
                f"""
                SELECT caso, COUNT(DISTINCT id), SUM(total_caracteres)
                FROM {Tabla.DOCUMENTOS}
                GROUP BY caso
                ORDER BY COUNT(DISTINCT id) DESC
                """
            )
            filas = cursor.fetchall()
        return [
            {"caso": caso, "total_documentos": documentos, "total_caracteres": caracteres}
            for caso, documentos, caracteres in filas
        ]

    def columnas_de(self, tabla: Tabla) -> list[str]:
        with self._cursor() as cursor:
            cursor.execute(f"PRAGMA table_info({tabla})")
            return [columna[1] for columna in cursor.fetchall()]

    def muestra_documentos(self, limite: int) -> list[tuple[Any, ...]]:
        with self._cursor() as cursor:
            cursor.execute(
                "SELECT id, caso, file_name, confianza_promedio, total_caracteres "
                f"FROM {Tabla.DOCUMENTOS} LIMIT ?",
                (limite,),
            )
            return [tuple(fila) for fila in cursor.fetchall()]

    def muestra_chunks(self, limite: int) -> list[tuple[Any, ...]]:
        """Filas (id, doc_id, chunk_index, longitud_texto, dimension_embedding)."""
        with self._cursor() as cursor:
            cursor.execute(
                f"SELECT id, doc_id, chunk_index, length(chunk_text), embedding "
                f"FROM {Tabla.CHUNKS} LIMIT ?",
                (limite,),
            )
            filas = cursor.fetchall()
        return [(*columnas, len(json.loads(embedding))) for *columnas, embedding in filas]
