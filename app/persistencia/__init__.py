"""Almacenamiento de documentos y chunks vectoriales (pgvector, con respaldo SQLite)."""

from app.persistencia.almacen import almacen_documental

__all__ = ["almacen_documental"]
