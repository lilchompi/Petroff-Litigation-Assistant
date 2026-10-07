"""Las reglas sin LLM, con los casos reales que salieron de los 43 JSONL."""

from app.revision.indices import es_fragmento_de, indices_en
from app.revision.motor import IndiceMatters, Revision
from app.revision.nombres import leer_nombre, mismo_nombre, normalizar_index
from app.revision.plan import FUSIONAR, RENOMBRAR
from app.validacion.inventario_jsonl import ArchivoJsonl

CARPETAS = {
    "Choi, Younga - Closed - 800410 - 0": "choi-viejo",
    "Choi, Younga T. - 800012 - 2-25-cv-00985": "choi-nuevo",
    "Jenkins, Brittney - 800066 - 0": "jenkins",
    "Luciano, Katherine - 600847 - 505349-2023": "luciano",
    "Kooperling, Matias - 800313 - 0": "koop-viejo",
    "Matias, Kooperling - 800313 - 1-26-cv-03144": "koop-nuevo",
    "1738 East 4th Street LLC - 200026 - 0": "1738",
    "Cato, Lamar - Closed - 100017 - 0": "cato-viejo",
    "Anderson, Howiya - 900082 - 501593-2026": "anderson",
    "Forman, Ryan - 900038 - 623227-2025": "forman",
    "Anicet, Osier - 600957 - 508190-2013": "anicet",
    "Breuer, Arthur - 600117 - 508190-2013": "breuer",
    "Becker, Michael - 100005 - 607182-2025": "becker",
    "Becker, Michael - Closed - 100018 - 607182-2025": "becker-cerrada",
    "Hernandez, Nelson - Closed - 900052 - 0": "hernandez-1",
    "Hernandez, Nelson - Closed - 900067 - 0": "hernandez-2",
    "Hernandez, Nelson - Closed - 900272 - 0": "hernandez-3",
}


def _doc(nombre: str, *indices: str) -> ArchivoJsonl:
    return ArchivoJsonl(
        linea=1, caso=None, id=f"id-{nombre}", carpeta="", nombre=nombre, tamano_mb=0.1,
        hash="", leido=True, motivo_no_leido="", indices_caratula=frozenset(indices),
    )  # fmt: skip


def _revisar(carpeta_id: str, *docs: ArchivoJsonl) -> Revision:
    revision = Revision(IndiceMatters(CARPETAS))
    revision.revisar(carpeta_id, list(docs))
    revision.cerrar()
    return revision


def test_index_normalizados_y_ruido():
    assert normalizar_index("1-23-cv-1270") == normalizar_index("1:23-cv-01270") == "1:23-cv-01270"
    assert normalizar_index("826173-2025") == "826173/2025"
    assert normalizar_index("0") is None
    assert "2019/2020" not in indices_en("statements for 2019/2020")
    assert es_fragmento_de("593/2026", "501593/2026")
    assert not es_fragmento_de("623227/2025", "501593/2026")


def test_mismo_nombre_ignora_orden_y_palabras_de_mas():
    assert mismo_nombre(
        leer_nombre("Kooperling, Matias - 800313 - 0"),
        leer_nombre("Matias, Kooperling - 800313 - 0"),
    )
    assert mismo_nombre(leer_nombre("Choi, Younga - 1 - 0"), leer_nombre("Choi, Younga T. - 2 - 0"))
    assert not mismo_nombre(
        leer_nombre("Jenkins, Brittney - 1 - 0"), leer_nombre("Luciano, Katherine - 2 - 0")
    )


def test_regla_5_mismo_id_mismo_nombre_fusiona():
    revision = _revisar("koop-viejo")
    [accion] = revision.plan.acciones
    assert accion.tipo == FUSIONAR
    assert (accion.datos["origen_id"], accion.datos["destino_id"]) == ("koop-viejo", "koop-nuevo")


def test_regla_6_choi_se_fusiona_por_ocr():
    revision = _revisar("choi-viejo", *[_doc(f"doc{i}.pdf", "2:25-cv-00985") for i in range(9)])
    [accion] = revision.plan.acciones
    assert accion.tipo == FUSIONAR and accion.regla == "6_ocr_confirma_index"
    assert accion.datos["destino_id"] == "choi-nuevo"
    assert accion.datos["eliminar_origen"]


def test_regla_6_jenkins_no_se_fusiona_con_luciano():
    revision = _revisar("jenkins", _doc("TRO- Luciano.docx", "505349/2023"), _doc("foto.jpg"))
    assert not revision.plan.acciones
    [hallazgo] = [h for h in revision.plan.hallazgos if h.regla == "4_documento_de_otro_cliente"]
    assert hallazgo.para_llm and hallazgo.datos["file_name"] == "TRO- Luciano.docx"


def test_regla_4_renombra_con_dos_documentos_y_sugiere_con_uno():
    revision = _revisar("1738", _doc("a.pdf", "1:23-cv-01270"), _doc("b.pdf", "1:23-cv-01270"))
    [accion] = revision.plan.acciones
    assert accion.tipo == RENOMBRAR
    assert accion.datos["nombre_nuevo"] == "1738 East 4th Street LLC - 200026 - 1-23-cv-01270"

    revision = _revisar("1738", _doc("a.pdf", "1:23-cv-01270"))
    assert not revision.plan.acciones
    assert [h.regla for h in revision.plan.hallazgos] == ["4_index_sugerido"]


def test_regla_8_plantilla_mal_editada_solo_avisa():
    docs = [_doc(f"Anderson motion {i}.pdf", "501593/2026") for i in range(5)]
    docs.append(_doc("Draft_stipulationofDiscontinuance_Anderson.docx", "623227/2025"))
    revision = _revisar("anderson", *docs)
    assert not revision.plan.acciones
    [hallazgo] = [
        h for h in revision.plan.hallazgos if h.regla == "8_index_equivocado_en_documento"
    ]
    assert hallazgo.datos["found_index_belongs_to"] == "Forman, Ryan - 900038 - 623227-2025"
    assert not hallazgo.para_llm


def test_regla_7_codemandados_no_se_fusionan_y_mismo_cliente_si():
    revision = _revisar("anicet", _doc("order.pdf", "508190/2013"))
    assert not revision.plan.acciones
    assert any(
        h.regla == "7_mismo_index_otro_cliente" and h.para_llm for h in revision.plan.hallazgos
    )

    revision = _revisar("becker-cerrada", _doc("order.pdf", "607182/2025"))
    [accion] = revision.plan.acciones
    assert (accion.datos["origen_id"], accion.datos["destino_id"]) == ("becker-cerrada", "becker")


def test_hernandez_tres_carpetas_con_el_mismo_index_no_se_renombran():
    revision = Revision(IndiceMatters(CARPETAS))
    for carpeta in ("hernandez-1", "hernandez-2", "hernandez-3"):
        revision.revisar(carpeta, [_doc(f"{carpeta}-{i}.docx", "2:24-cv-08186") for i in range(5)])
    revision.cerrar()
    assert not revision.plan.acciones
    [hallazgo] = [h for h in revision.plan.hallazgos if h.regla == "7_cliente_en_varias_carpetas"]
    assert len(hallazgo.datos["carpetas"]) == 3  # noqa: PLR2004
