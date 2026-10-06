"""Pruebas del validador JSONL vs SharePoint (por id), sin conexión a SharePoint."""

import json
from pathlib import Path

from app.sharepoint import ArchivoSharePoint
from app.validacion import comparar, informe_texto, leer_inventario

CASO = "Adeyemi - Closed - 601243 - 0"
MB = 2**20


def _sp(id_: str, carpeta: str, nombre: str, mb: float = 0.5) -> ArchivoSharePoint:
    return ArchivoSharePoint(id_, carpeta, nombre, int(mb * MB), f"h-{id_}", "")


def _jsonl(ruta: Path, registros: list[dict], cabecera: dict | None = None) -> Path:
    lineas = ([cabecera] if cabecera else []) + registros
    ruta.write_text("\n".join(json.dumps(r) for r in lineas), encoding="utf-8")
    return ruta


def _registro(id_: str | None, carpeta: str, nombre: str, **extra) -> dict:
    registro = {
        "caso": CASO,
        "file_name": nombre,
        "subfolder": "(folder root)",
        "origen": f"/Matters/{CASO}/{carpeta}".rstrip("/"),
        "size_mb": 0.5,
        "was_read": True,
        **extra,
    }
    if id_:
        registro["id"] = id_
    return registro


def _resultado(tmp_path: Path, registros: list[dict], sharepoint: list[ArchivoSharePoint]):
    archivos = leer_inventario(_jsonl(tmp_path / "c.jsonl", registros)).archivos
    return comparar(CASO, sharepoint, archivos, ["Claude-*.jsonl"])


def test_lee_caso_carpeta_e_id(tmp_path):
    ruta = _jsonl(tmp_path / "c.jsonl", [_registro("X1", "03_Litigation/TRO", "TRO.docx")])
    inventario = leer_inventario(ruta)
    assert list(inventario.por_caso()) == [CASO]
    assert (inventario.archivos[0].id, inventario.archivos[0].ruta) == (
        "X1",
        "03_Litigation/TRO/TRO.docx",
    )


def test_completo_cuando_todos_los_ids_estan(tmp_path):
    resultado = _resultado(
        tmp_path,
        [_registro("1", "A", "a.pdf"), _registro("2", "", "b.pdf")],
        [_sp("1", "A", "a.pdf"), _sp("2", "", "b.pdf"), _sp("9", "", "Claude-601243.jsonl")],
    )
    assert resultado.completo
    assert [a.nombre for a in resultado.ignorados] == ["Claude-601243.jsonl"]


def test_faltantes_agrupados_por_carpeta(tmp_path):
    sharepoint = [
        _sp("1", "03_Litigation", "a.pdf"),
        _sp("2", "03_Litigation/TRO", "TRO.docx"),
        _sp("3", "03_Litigation/TRO", "AOS.docx"),
        _sp("4", "", "nota.pdf"),
    ]
    resultado = _resultado(tmp_path, [_registro("1", "03_Litigation", "a.pdf")], sharepoint)

    assert not resultado.completo
    por_carpeta = {k: [a.nombre for a in v] for k, v in resultado.faltantes_por_carpeta().items()}
    assert por_carpeta == {
        "(raíz del caso)": ["nota.pdf"],
        "03_Litigation/TRO": ["AOS.docx", "TRO.docx"],
    }
    assert "FALTAN EN EL JSONL (3)" in informe_texto(resultado)


def test_mismo_nombre_pero_otro_id_es_faltante_y_sobrante(tmp_path):
    # Alguien borró TRO.docx y subió otro con el mismo nombre: por id no es el mismo.
    resultado = _resultado(
        tmp_path, [_registro("viejo", "TRO", "TRO.docx")], [_sp("nuevo", "TRO", "TRO.docx")]
    )
    assert [a.id for a in resultado.faltantes] == ["nuevo"]
    assert [a.id for a in resultado.sobrantes] == ["viejo"]


def test_lineas_sin_id_hacen_incompleta_la_validacion(tmp_path):
    resultado = _resultado(
        tmp_path,
        [_registro("1", "", "a.pdf"), _registro(None, "", "b.pdf")],
        [_sp("1", "", "a.pdf")],
    )
    assert not resultado.completo
    assert [a.nombre for a in resultado.sin_id] == ["b.pdf"]
    assert "1 línea(s) del JSONL sin id" in informe_texto(resultado)


def test_movidos_duplicados_tamano_y_no_leidos(tmp_path):
    resultado = _resultado(
        tmp_path,
        [
            _registro("1", "Viejo", "x.pdf"),
            _registro("1", "Viejo", "x.pdf"),
            _registro("2", "", "grande.pdf", size_mb=1.0),
            _registro("3", "", "roto.7z", was_read=False, not_read_because="no reader for .7z"),
        ],
        [_sp("1", "Nuevo", "x2.pdf"), _sp("2", "", "grande.pdf", mb=3.0), _sp("3", "", "roto.7z")],
    )
    assert resultado.completo
    assert [(e.jsonl.ruta, e.sharepoint.ruta) for e in resultado.movidos] == [
        ("Viejo/x.pdf", "Nuevo/x2.pdf")
    ]
    assert len(resultado.duplicados) == 1
    assert [e.sharepoint.nombre for e in resultado.tamano_distinto] == ["grande.pdf"]
    assert [a.motivo_no_leido for a in resultado.no_leidos] == ["no reader for .7z"]


def test_resumen_por_carpeta_incluye_las_completas(tmp_path):
    resultado = _resultado(
        tmp_path,
        [_registro("1", "A", "a.pdf"), _registro("2", "B", "b.pdf")],
        [_sp("1", "A", "a.pdf"), _sp("2", "B", "b.pdf"), _sp("3", "B", "c.pdf")],
    )
    assert resultado.resumen_por_carpeta() == [
        {"carpeta": "A", "en_sharepoint": 1, "en_jsonl": 1, "faltan": 0},
        {"carpeta": "B", "en_sharepoint": 2, "en_jsonl": 1, "faltan": 1},
    ]
    assert "POR CARPETA:" in informe_texto(resultado)
