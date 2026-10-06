"""El servicio con un JSONL de varios casos, contra un SharePoint simulado."""

import json

from app.core.config import settings
from app.servicios.validacion import validar_jsonl_contra_sharepoint
from app.sharepoint import ArchivoSharePoint, CasoNoEncontradoError

SHAREPOINT = {
    "Alvarez, Brianna - Closed - 400029 - 0": [
        ArchivoSharePoint("a1", "01_General", "a.pdf", 100, "", ""),
        ArchivoSharePoint("a2", "03_Litigation", "b.pdf", 100, "", ""),
    ],
    "Allard v. Petroff - 500291 - 0": [ArchivoSharePoint("b1", "", "c.pdf", 100, "", "")],
}


class SharePointFalso:
    def resolver_caso(self, caso: str) -> str:
        for nombre in SHAREPOINT:
            if nombre.replace("Closed - ", "") == caso or nombre == caso:
                return nombre
        raise CasoNoEncontradoError(f"No existe la carpeta '{caso}' en Matters/")

    def listar_caso(self, caso: str) -> list[ArchivoSharePoint]:
        return SHAREPOINT[caso]


def _linea(caso: str, id_: str, nombre: str) -> str:
    return json.dumps({"id": id_, "caso": caso, "file_name": nombre, "was_read": True})


def test_valida_cada_caso_del_jsonl_contra_su_carpeta(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "VALIDACIONES_DIR", tmp_path / "validaciones")
    jsonl = tmp_path / "varios.jsonl"
    jsonl.write_text(
        "\n".join(
            [
                _linea("Alvarez, Brianna - 400029 - 0", "a1", "a.pdf"),
                _linea("Allard v. Petroff - 500291 - 0", "b1", "c.pdf"),
                _linea("Caso Borrado - 999999 - 0", "z1", "z.pdf"),
            ]
        ),
        encoding="utf-8",
    )

    validacion = validar_jsonl_contra_sharepoint(jsonl, cliente=SharePointFalso())

    por_caso = {r.caso: r for r in validacion.resultados}
    alvarez = por_caso["Alvarez, Brianna - Closed - 400029 - 0"]
    assert [a.id for a in alvarez.faltantes] == ["a2"]
    assert alvarez.caso_solicitado == "Alvarez, Brianna - 400029 - 0"
    assert por_caso["Allard v. Petroff - 500291 - 0"].completo
    assert list(validacion.errores) == ["Caso Borrado - 999999 - 0"]
    assert not validacion.completo

    texto = validacion.informe_txt.read_text(encoding="utf-8")
    assert "Casos en el JSONL: 3" in texto
    assert "NO EXISTE" in texto
    guardado = json.loads(validacion.informe_json.read_text(encoding="utf-8"))
    assert len(guardado["casos"]) == len(validacion.resultados)
