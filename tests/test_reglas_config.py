"""Las opciones de config/reglas_revision.toml cambian el comportamiento como se espera."""

from app.revision.motor import IndiceMatters, Revision
from app.revision.reglas import Reglas, cargar_reglas
from app.validacion.inventario_jsonl import ArchivoJsonl

CARPETAS = {
    "Banni, Sr., David - 400003 - 157104-2026": "banni",
    "Delgado, Julio - 601003 - 725562-2022": "delgado",
    "Duran, Luz - 200009 - 709157-2024": "duran-art15",
    "Duran, Luz - 600246 - 710731-2015": "duran-foreclosure",
    "Gao, Wen - Closed - 800014 - 0": "gao-viejo",
    "Gao, Wenzhen - 800434 - 1-25-cv-03075": "gao",
}
ACTIVAS = Reglas(
    anios_en_el_futuro=1,
    un_digito_distinto_es_ocr=True,
    index_sin_carpeta_minimo_documentos=3,
    mismo_cliente_otro_caso_es_informativo=True,
    alias=(frozenset({"Gao, Wen", "Gao, Wenzhen"}),),
)


def _doc(nombre: str, *indices: str) -> ArchivoJsonl:
    return ArchivoJsonl(
        linea=1, caso=None, id=f"id-{nombre}", carpeta="", nombre=nombre, tamano_mb=0.1,
        hash="", leido=True, motivo_no_leido="", indices_caratula=frozenset(indices),
    )  # fmt: skip


def _reglas_de(carpeta_id: str, reglas: Reglas, *docs: ArchivoJsonl) -> Revision:
    revision = Revision(IndiceMatters(CARPETAS), reglas=reglas)
    revision.revisar(carpeta_id, list(docs))
    revision.cerrar()
    return revision


def test_el_archivo_del_repo_se_lee():
    reglas = cargar_reglas()
    assert reglas.version != "por-defecto"
    assert "15109/2013" in reglas.citas_conocidas


def test_ruido_anio_futuro_y_un_digito():
    docs = [_doc("Trans Union LLC.pdf", "6714/2030"), _doc("a.pdf", "157104/2026")]
    assert any(
        h.regla == "6_index_sin_carpeta"
        for h in _reglas_de("banni", Reglas(), *docs).plan.hallazgos
    )
    assert not _reglas_de("banni", ACTIVAS, *docs).plan.hallazgos

    docs = [_doc("Affd service Delgado.pdf", "726562/2022"), _doc("b.pdf", "725562/2022")]
    assert not _reglas_de("delgado", ACTIVAS, *docs).plan.hallazgos


def test_mismo_cliente_otro_caso_informativo_salvo_descarga_de_nyscef():
    docs = [_doc(f"Affirmation in Opposition _ Duran {i}.pdf", "709157/2024") for i in range(3)]
    docs.append(_doc("Decision dismissing foreclosure.pdf", "710731/2015"))
    docs.append(_doc("710731_2015_Deutsche_v_Duran_ORDER_12.pdf", "710731/2015"))
    hallazgos = _reglas_de("duran-art15", ACTIVAS, *docs).plan.hallazgos
    reglas = sorted(h.regla for h in hallazgos)
    assert reglas == ["4_documento_de_otro_caso_del_cliente", "4_relacion_entre_casos_informativo"]
    pendiente = next(h for h in hallazgos if h.para_llm)
    assert pendiente.datos["file_name"].startswith("710731_2015_")


def test_alias_permite_fusionar_gao():
    docs = [_doc(f"doc{i}.pdf", "1:25-cv-03075") for i in range(3)]
    assert not _reglas_de("gao-viejo", Reglas(), *docs).plan.acciones
    [accion] = _reglas_de("gao-viejo", ACTIVAS, *docs).plan.acciones
    assert accion.datos["destino_id"] == "gao"
