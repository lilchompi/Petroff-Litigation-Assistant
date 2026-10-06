"""Fachada de almacenamiento: PostgreSQL como motor principal y SQLite como respaldo local.

SQLite siempre recibe una copia de cada documento para garantizar persistencia offline;
PostgreSQL se usa para escritura y búsqueda cuando está disponible.
"""

import logging
from typing import Any

import psycopg2

from app.core.config import Settings, settings
from app.persistencia.modelos import ChunkVectorial, FragmentoRecuperado, Tabla
from app.persistencia.repositorio_postgres import RepositorioPostgres
from app.persistencia.repositorio_sqlite import RepositorioSqlite

logger = logging.getLogger(__name__)

IDENTIFICADOR_MOTOR_POSTGRES = "pgvector"
IDENTIFICADOR_MOTOR_SQLITE = "sqlite-vec-local"
DESCRIPCION_MOTOR_POSTGRES = "PostgreSQL (pgvector)"
DESCRIPCION_MOTOR_SQLITE = "SQLite-Vec (Local Fallback)"


def _conectar_postgres(configuracion: Settings) -> RepositorioPostgres | None:
    try:
        repositorio = RepositorioPostgres.conectar(configuracion)
    except psycopg2.Error as error:
        logger.info("PostgreSQL no disponible (%s). Se usará el almacén local SQLite.", error)
        return None
    logger.info("Conectado a PostgreSQL + pgvector.")
    return repositorio


class AlmacenDocumental:
    def __init__(self, configuracion: Settings) -> None:
        self.sqlite = RepositorioSqlite(configuracion.SQLITE_PATH)
        self.postgres = _conectar_postgres(configuracion)

    @property
    def usa_postgres(self) -> bool:
        return self.postgres is not None

    @property
    def identificador_motor(self) -> str:
        return IDENTIFICADOR_MOTOR_POSTGRES if self.usa_postgres else IDENTIFICADOR_MOTOR_SQLITE

    @property
    def descripcion_motor(self) -> str:
        return DESCRIPCION_MOTOR_POSTGRES if self.usa_postgres else DESCRIPCION_MOTOR_SQLITE

    def guardar_documento_y_chunks(
        self, documento: dict[str, Any], chunks: list[ChunkVectorial]
    ) -> None:
        if self.postgres:
            try:
                self.postgres.guardar_documento_y_chunks(documento, chunks)
            except psycopg2.Error:
                logger.exception("Error guardando el documento %s en PostgreSQL.", documento["id"])
        self.sqlite.guardar_documento_y_chunks(documento, chunks)

    def busqueda_vectorial(
        self, embedding_consulta: list[float], caso: str | None, top_k: int
    ) -> list[FragmentoRecuperado]:
        if self.postgres:
            try:
                return self.postgres.busqueda_vectorial(embedding_consulta, caso, top_k)
            except psycopg2.Error:
                logger.exception("Error en la búsqueda PostgreSQL; se consulta SQLite.")
        return self.sqlite.busqueda_vectorial(embedding_consulta, caso, top_k)

    def listar_casos(self) -> list[dict[str, Any]]:
        return self.sqlite.listar_casos()

    def contar_registros(self, tabla: Tabla) -> int:
        repositorio = self.postgres or self.sqlite
        return repositorio.contar_registros(tabla)


almacen_documental = AlmacenDocumental(settings)
