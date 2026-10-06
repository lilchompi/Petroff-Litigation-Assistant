"""Routers de FastAPI agrupados por recurso."""

from app.api.rutas import casos, consulta, ingesta, interfaz, salud, validacion

ROUTERS = [
    salud.router,
    ingesta.router,
    validacion.router,
    consulta.router,
    casos.router,
    interfaz.router,
]
