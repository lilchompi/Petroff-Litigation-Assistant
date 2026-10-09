"""Limpieza en memoria de un JSONL por caso: reglas 1-4, sin enmascarar PII."""

import json

from app.limpieza.jsonl import limpiar_jsonl

TEXTO = (
    "SUPREME COURT OF THE STATE OF NEW YORK\nIndex No. 612345/2023\n"
    "The defendant failed to pro-\nvide the notice required under\nRPAPL 1304. "
    "SSN 123-45-6789, tel (718) 555-1234."
)


def _jsonl(*registros) -> bytes:
    return "".join(json.dumps(r) + "\n" for r in registros).encode("utf-8")


def _doc(sharepoint_id, texto=TEXTO, leido=True):
    return {
        "sharepoint_id": sharepoint_id,
        "file_name": f"{sharepoint_id}.pdf",
        "was_read": leido,
        "read_with": "PaddleOCR (mean confidence 0.99)",
        "extracted_text": texto,
        "extracted_text_length": len(texto),
    }


DOCUMENTOS = 3
CABECERA = {
    "matter": "Caso - 600001 - 612345-2023",
    "files_in_matter": DOCUMENTOS,
    "coverage": 1.333,
}


def test_limpia_sin_enmascarar_y_conserva_las_lineas():
    limpio = limpiar_jsonl(_jsonl(CABECERA, _doc("a"), _doc("b", "@@##"), _doc("c", "", False)))
    textos = {d["sharepoint_id"]: d for d in limpio.lineas}

    assert "123-45-6789" in textos["a"]["extracted_text"]  # sin regla 5
    assert "(718) 555-1234" in textos["a"]["extracted_text"]
    assert "provide" in textos["a"]["extracted_text"]  # regla 3: des-guionado
    assert textos["b"]["extracted_text"] == ""  # regla 1: basura
    assert textos["b"]["cleaning_discarded_because"]
    assert len(limpio.lineas) == DOCUMENTOS  # nada se borra: coverage sigue cuadrando
    assert limpio.resumen.limpiados == 1
    assert limpio.resumen.no_leidos == 1
    assert limpio.cabecera["cleaning"]["pii_masked"] is False


def test_quita_duplicados_y_corrige_coverage():
    corto = _doc("a", TEXTO[:40])
    limpio = limpiar_jsonl(_jsonl(CABECERA, corto, _doc("b"), _doc("a"), _doc("c")))

    assert limpio.resumen.duplicados_quitados == 1
    assert [d["sharepoint_id"] for d in limpio.lineas] == ["a", "b", "c"]
    assert "provide" in limpio.lineas[0]["extracted_text"]  # se queda la de más texto
    assert limpio.cabecera["files_described"] == DOCUMENTOS
    assert limpio.cabecera["coverage"] == 1.0


def test_contenido_es_un_jsonl_valido():
    limpio = limpiar_jsonl(_jsonl(CABECERA, _doc("a")))
    lineas = limpio.contenido().decode("utf-8").splitlines()
    assert json.loads(lineas[0])["matter"] == CABECERA["matter"]
    assert json.loads(lineas[1])["sharepoint_id"] == "a"
