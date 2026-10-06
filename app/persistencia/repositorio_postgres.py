"""Almacén vectorial en PostgreSQL con la extensión pgvector."""

from collections.abc import Iterator
from contextlib import contextmanager

import psycopg2
from psycopg2.extensions import connection
from psycopg2.extras import RealDictCursor

from app.core.config import Settings
from app.persistencia.modelos import (
    COLUMNAS_DOCUMENTO,
    FragmentoRecuperado,
    Tabla,
    sql_insercion,
)
from app.persistencia.repositorio_base import RepositorioSqlBase

HNSW_CONEXIONES_POR_NODO = 16
HNSW_CANDIDATOS_EN_CONSTRUCCION = 64


def _sql_esquema(dimension_embedding: int) -> str:
    return f"""
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS {Tabla.DOCUMENTOS} (
    id VARCHAR(64) PRIMARY KEY,
    caso VARCHAR(255) NOT NULL,
    file_name VARCHAR(255) NOT NULL,
    subfolder VARCHAR(255),
    size_mb FLOAT,
    origen TEXT,
    document_type VARCHAR(100),
    contains_ssn BOOLEAN,
    confianza_promedio FLOAT,
    total_caracteres INT,
    texto_limpio TEXT NOT NULL,
    metadata JSONB,
    fecha_procesamiento TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS {Tabla.CHUNKS} (
    id SERIAL PRIMARY KEY,
    doc_id VARCHAR(64) REFERENCES {Tabla.DOCUMENTOS}(id) ON DELETE CASCADE,
    caso VARCHAR(255) NOT NULL,
    file_name VARCHAR(255) NOT NULL,
    subfolder VARCHAR(255),
    chunk_index INT NOT NULL,
    chunk_text TEXT NOT NULL,
    embedding vector({dimension_embedding}) NOT NULL,
    metadata JSONB
);

CREATE INDEX IF NOT EXISTS idx_chunks_embedding
ON {Tabla.CHUNKS}
USING hnsw (embedding vector_cosine_ops)
WITH (m = {HNSW_CONEXIONES_POR_NODO}, ef_construction = {HNSW_CANDIDATOS_EN_CONSTRUCCION});

CREATE INDEX IF NOT EXISTS idx_chunks_caso ON {Tabla.CHUNKS} (caso);
"""


class RepositorioPostgres(RepositorioSqlBase):
    MARCADOR_PARAMETRO = "%s"
    SQL_UPSERT_DOCUMENTO = (
        sql_insercion(Tabla.DOCUMENTOS, COLUMNAS_DOCUMENTO, "%s")
        + " ON CONFLICT (id) DO UPDATE SET texto_limpio = EXCLUDED.texto_limpio"
    )

    def __init__(self, conexion: connection) -> None:
        self._conexion = conexion

    @classmethod
    def conectar(cls, configuracion: Settings) -> "RepositorioPostgres":
        """Abre la conexión y garantiza que el esquema exista. Lanza psycopg2.Error si falla."""
        conexion = psycopg2.connect(
            host=configuracion.POSTGRES_HOST,
            port=configuracion.POSTGRES_PORT,
            dbname=configuracion.POSTGRES_DB,
            user=configuracion.POSTGRES_USER,
            password=configuracion.POSTGRES_PASSWORD,
            connect_timeout=configuracion.POSTGRES_CONNECT_TIMEOUT_SEGUNDOS,
        )
        repositorio = cls(conexion)
        with repositorio._cursor() as cursor:
            cursor.execute(_sql_esquema(configuracion.EMBEDDING_DIM))
        return repositorio

    @contextmanager
    def _cursor(self) -> Iterator[RealDictCursor]:
        with self._conexion, self._conexion.cursor(cursor_factory=RealDictCursor) as cursor:
            yield cursor

    def _serializar_embedding(self, embedding: list[float]) -> list[float]:
        return embedding

    def busqueda_vectorial(
        self, embedding_consulta: list[float], caso: str | None, top_k: int
    ) -> list[FragmentoRecuperado]:
        filtro_caso = "WHERE caso ILIKE %(caso)s" if caso else ""
        consulta = f"""
            SELECT doc_id, caso, file_name, subfolder, chunk_index, chunk_text,
                   1 - (embedding <=> %(embedding)s::vector) AS similitud
            FROM {Tabla.CHUNKS}
            {filtro_caso}
            ORDER BY embedding <=> %(embedding)s::vector
            LIMIT %(limite)s
        """
        parametros = {"embedding": embedding_consulta, "caso": f"%{caso}%", "limite": top_k}
        with self._cursor() as cursor:
            cursor.execute(consulta, parametros)
            return [FragmentoRecuperado(**fila) for fila in cursor.fetchall()]
