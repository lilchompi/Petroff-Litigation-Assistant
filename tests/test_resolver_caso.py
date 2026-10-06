"""Encontrar la carpeta del caso aunque su nombre haya cambiado (p. ej. al cerrarse)."""

import pytest

from app.sharepoint import CasoNoEncontradoError, ClienteGraph

CARPETAS = [
    "Alvarez, Brianna - Closed - 400029 - 0",
    "Allard v. Petroff - 500291 - 109248-2005",
    "Gomez - 700001 - 0",
    "Gomez Otra - Closed - 700001 - 1",
]


@pytest.fixture
def cliente(monkeypatch) -> ClienteGraph:
    monkeypatch.setattr("app.core.config.settings.GRAPH_TENANT_ID", "t")
    monkeypatch.setattr("app.core.config.settings.GRAPH_CLIENT_ID", "c")
    monkeypatch.setattr("app.core.config.settings.GRAPH_CLIENT_SECRET", "s")
    cliente = ClienteGraph()
    cliente._casos = {nombre: f"id-{i}" for i, nombre in enumerate(CARPETAS)}
    return cliente


def test_nombre_exacto(cliente):
    assert cliente.resolver_caso(CARPETAS[1]) == CARPETAS[1]


def test_caso_que_se_cerro_despues(cliente):
    assert cliente.resolver_caso("Alvarez, Brianna - 400029 - 0") == CARPETAS[0]


def test_por_numero_si_el_nombre_del_cliente_cambio(cliente):
    assert cliente.resolver_caso("Allard - 500291 - 0") == CARPETAS[1]


def test_no_adivina_si_hay_varias_con_el_mismo_numero(cliente):
    with pytest.raises(CasoNoEncontradoError, match="varias parecidas"):
        cliente.resolver_caso("Perez - 700001 - 9")


def test_caso_inexistente(cliente):
    with pytest.raises(CasoNoEncontradoError, match="No existe la carpeta"):
        cliente.resolver_caso("Nadie - 123456 - 0")
