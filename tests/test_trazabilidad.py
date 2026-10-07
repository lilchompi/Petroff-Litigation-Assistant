"""Trazabilidad: estado de cada carpeta y porcentaje de limpieza."""

from app.revision.plan import FUSIONAR, RENOMBRAR, Accion, Hallazgo, Plan
from app.revision.trazabilidad import (
    COMPLEJA,
    FUSIONADA,
    INCOMPLETA,
    LIMPIA,
    POR_APLICAR,
    SIN_JSONL,
    Trazabilidad,
)

CARPETAS = {
    "castro": "Castro, Ramona - 900177 - 0",
    "cato-viejo": "Cato, Lamar - Closed - 100017 - 0",
    "cato": "Cato, Lamar - 100002 - 709633-2025",
    "angert": "Angert, Helen - 601109 - 508065-2026",
    "abbh": "ABBH - 700171 - 501955-2024",
    "incompleta": "Otro, Caso - 900999 - 0",
    "sin-jsonl": "Nadie, Aun - 900998 - 0",
}
RENOMBRE = Accion(
    RENOMBRAR, "4", "m",
    {"carpeta_id": "castro", "nombre_actual": CARPETAS["castro"],
     "nombre_nuevo": "Castro, Ramona - 900177 - 2-24-cv-03321"},
)  # fmt: skip
FUSION = Accion(
    FUSIONAR, "6", "m",
    {"origen_id": "cato-viejo", "origen_nombre": CARPETAS["cato-viejo"],
     "destino_id": "cato", "destino_nombre": CARPETAS["cato"]},
)  # fmt: skip


def _cobertura(faltan: int = 0) -> dict[str, int]:
    return {"archivos_sharepoint": 10, "archivos_jsonl": 10 - faltan, "faltan": faltan}


def test_estados_porcentaje_y_persistencia(tmp_path):
    traza = Trazabilidad(tmp_path)
    traza.sincronizar({i: t for i, t in CARPETAS.items()})
    plan = Plan(
        acciones=[RENOMBRE, FUSION],
        hallazgos=[Hallazgo("6_varios_casos", "x", CARPETAS["angert"], para_llm=True)],
    )
    cobertura = {i: _cobertura() for i in ("castro", "cato-viejo", "angert", "abbh")}
    cobertura["incompleta"] = _cobertura(faltan=3)
    traza.registrar_revision(plan, cobertura, {t: i for i, t in CARPETAS.items()})

    estados = {i: f["estado"] for i, f in traza.filas.items()}
    assert estados == {
        "castro": POR_APLICAR, "cato-viejo": POR_APLICAR, "cato": SIN_JSONL,
        "angert": COMPLEJA, "abbh": LIMPIA, "incompleta": INCOMPLETA, "sin-jsonl": SIN_JSONL,
    }  # fmt: skip

    traza.registrar_aplicadas([RENOMBRE, FUSION])
    traza.guardar()

    recargada = Trazabilidad(tmp_path)
    assert recargada.filas["castro"]["estado"] == LIMPIA
    assert recargada.filas["castro"]["carpeta"].endswith("2-24-cv-03321")
    assert recargada.filas["cato-viejo"]["estado"] == FUSIONADA
    assert recargada.filas["cato-viejo"]["fusionada_en"] == CARPETAS["cato"]
    resumen = "\n".join(recargada.resumen())
    assert "Carpetas de caso:          6" in resumen  # la fusionada ya no cuenta
    assert "LIMPIAS:                       2    33.3%" in resumen
    assert "REVISION" in recargada.ruta_log.read_text(encoding="utf-8")
