"""Las tareas para HubSpot que deja cada cambio aplicado."""

import csv

from app.revision.plan import FUSIONAR, RENOMBRAR, Accion
from app.revision.tareas_hubspot import anotar, cancelacion, tarea_de


def test_renombre_y_fusion_generan_tareas_legibles(tmp_path):
    renombre = Accion(
        RENOMBRAR, "4_index_desde_ocr", "2 documentos de corte llevan 2:24-cv-03321",
        {"carpeta_id": "x", "nombre_actual": "Castro, Ramona - 900177 - 0",
         "nombre_nuevo": "Castro, Ramona - 900177 - 2-24-cv-03321"},
    )  # fmt: skip
    fusion = Accion(
        FUSIONAR, "6_ocr_confirma_index", "1 documento lleva 709633/2025",
        {"origen_nombre": "Cato, Lamar - Closed - 100017 - 0",
         "destino_nombre": "Cato, Lamar - 100002 - 709633-2025"},
    )  # fmt: skip
    ruta = tmp_path / "tareas.csv"
    anotar(ruta, [tarea_de(renombre), tarea_de(fusion)])
    anotar(ruta, [cancelacion("Castro, Ramona - 900177 - 2-24-cv-03321")])

    with ruta.open(encoding="utf-8-sig") as archivo:
        filas = list(csv.DictReader(archivo))
    assert [f["tarea"] for f in filas] == [
        "Actualizar index", "Dejar un solo Matter", "NO HACER (se deshizo)",
    ]  # fmt: skip
    assert filas[0]["campo_hubspot"] == "index_number"
    assert filas[0]["valor_nuevo"] == "2:24-cv-03321"
    assert filas[0]["id_interno"] == "900177"
    assert "100017" in filas[1]["que_hacer"] and "100002" in filas[1]["que_hacer"]
