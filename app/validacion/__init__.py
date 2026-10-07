"""Validación de que un JSONL de OCR cubre todos los archivos de sus casos en SharePoint."""

from app.validacion.comparador import Emparejado, ResultadoValidacion, comparar
from app.validacion.informe import informe_texto, informe_varios_casos
from app.validacion.inventario_jsonl import (
    ArchivoJsonl,
    InventarioJsonl,
    leer_inventario,
    leer_inventario_de_bytes,
)

__all__ = [
    "ArchivoJsonl",
    "Emparejado",
    "InventarioJsonl",
    "ResultadoValidacion",
    "comparar",
    "informe_texto",
    "informe_varios_casos",
    "leer_inventario",
    "leer_inventario_de_bytes",
]
