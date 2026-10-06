"""Routers de FastAPI agrupados por recurso."""

from app.api.rutas import casos, consulta, ingesta, interfaz, salud

ROUTERS = [salud.router, ingesta.router, consulta.router, casos.router, interfaz.router]
