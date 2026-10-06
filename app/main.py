"""Punto de entrada FastAPI del RAG Legal de Petroff Amshen LLP.

Endpoints:
- POST /api/limpiar-e-ingerir : Limpia el JSONL con las 5 reglas, lo vectoriza y lo almacena.
- POST /api/consulta          : Consulta jurídica al Agente Claude con búsqueda semántica.
- GET  /api/casos             : Lista los expedientes cargados.
- GET  /health                : Estado del servicio, motor vectorial y modelos.
- GET  /                      : Portal web de consulta.
"""

import logging

from fastapi import FastAPI

from app.api.rutas import ROUTERS
from app.core.constantes import NOMBRE_SERVICIO, VERSION_SERVICIO

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title=NOMBRE_SERVICIO,
    description=(
        "Limpieza especializada de OCR, vectorización en PostgreSQL (pgvector) "
        "y Agente Legal Claude."
    ),
    version=VERSION_SERVICIO,
)

for router in ROUTERS:
    app.include_router(router)
