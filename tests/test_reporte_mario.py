"""El reporte para Mario clasifica según la guía y no lleva texto de documentos."""

from app.revision.plan import FUSIONAR, RENOMBRAR, Accion, Hallazgo, Plan
from app.revision.reporte_mario import clasificar, generar_reporte

CARPETA = "Etienne, Francklin - 600740 - 543568-2025"


def _h(regla: str, **datos) -> Hallazgo:
    return Hallazgo(regla, "x", CARPETA, datos, para_llm=True)


def test_clasifica_segun_la_guia():
    plan = Plan(
        acciones=[
            Accion(FUSIONAR, "6", "m", {"origen_nombre": "Gawrych - 700176 - 0",
                                        "destino_nombre": "Gawrych - 900042 - 7-25-cv-02727"}),
            Accion(RENOMBRAR, "4", "m", {"nombre_actual": "a - 800427 - 0",
                                         "nombre_nuevo": "a - 800427 - 1-25-cv-00153"}),
        ],
        hallazgos=[
            _h("6_index_sin_carpeta", index="757/2010", documentos=["d"] * 68),
            _h("6_index_sin_carpeta", index="5101/2035", documentos=["d"]),
            _h("4_documento_de_otro_caso_del_cliente", file_name="AOS.docx",
               found_index="511607/2024", found_index_belongs_to="Etienne - 600937 - 511607-2024"),
            _h("4_documento_de_otro_caso_del_cliente", file_name="511607_2024_X_v_Y_ORDER.pdf",
               found_index="511607/2024", found_index_belongs_to="Etienne - 600937 - 511607-2024"),
            _h("4_documento_de_otro_cliente", file_name="Ex H - decision.pdf"),
        ],
    )  # fmt: skip
    c = clasificar(plan)
    assert len(c.fusiones) == 1 and len(c.aplicar) == 1
    assert [h.datos["index"] for h in c.casos_sin_carpeta] == ["757/2010"]
    assert [h.datos["index"] for h in c.ruido] == ["5101/2035"]
    assert len(c.referencias) == 1 and len(c.mover) == 1  # la descarga de NYSCEF sí se revisa
    assert len(c.anexos) == 1

    texto = generar_reporte(plan, "plan__prueba.json")
    assert "Tipos de caso distintos (7 y 9)" in texto
    assert "Nada de esto se ha aplicado" in texto
