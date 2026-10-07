"""Aplicar un plan y deshacerlo, contra un SharePoint simulado en memoria."""

from app.revision.ejecutor import Diario, Ejecutor, deshacer
from app.revision.plan import FUSIONAR, RENOMBRAR, Accion, Plan


class SharePointEnMemoria:
    """Lo mínimo del ClienteGraph que usa el ejecutor: {id: {name, padre, carpeta}}."""

    def __init__(self) -> None:
        self.items = {
            "matters": {"name": "Matters", "padre": None, "carpeta": True},
            "choi-viejo": {
                "name": "Choi, Younga - Closed - 800410 - 0",
                "padre": "matters",
                "carpeta": True,
            },
            "choi-nuevo": {
                "name": "Choi, Younga T. - 800012 - 2-25-cv-00985",
                "padre": "matters",
                "carpeta": True,
            },
            "complaint": {"name": "Complaint.docx", "padre": "choi-viejo", "carpeta": False},
            "discovery": {"name": "07_Discovery", "padre": "choi-viejo", "carpeta": True},
            "jsonl": {"name": "Claude-800410.jsonl", "padre": "choi-viejo", "carpeta": False},
            "1738": {
                "name": "1738 East 4th Street LLC - 200026 - 0",
                "padre": "matters",
                "carpeta": True,
            },
        }
        self._nuevos = 0

    def obtener(self, item_id):
        item = self.items[item_id]
        return {"id": item_id, "name": item["name"], "parentReference": {"id": item["padre"]}}

    def hijos(self, item_id):
        return [
            {"id": i, "name": d["name"]} for i, d in self.items.items() if d["padre"] == item_id
        ]

    def renombrar(self, item_id, nombre):
        self.items[item_id]["name"] = nombre

    def mover(self, item_id, padre_id):
        self.items[item_id]["padre"] = padre_id

    def eliminar(self, item_id):
        del self.items[item_id]

    def crear_carpeta(self, padre_id, nombre):
        for hijo in self.hijos(padre_id):
            if hijo["name"] == nombre:
                return hijo["id"], False
        self._nuevos += 1
        nuevo = f"nueva-{self._nuevos}"
        self.items[nuevo] = {"name": nombre, "padre": padre_id, "carpeta": True}
        return nuevo, True

    def estado(self):
        return {i: (d["name"], d["padre"]) for i, d in self.items.items()}


def _plan() -> Plan:
    return Plan(
        acciones=[
            Accion(
                FUSIONAR, "6_ocr_confirma_index", "prueba",
                {
                    "origen_id": "choi-viejo",
                    "origen_nombre": "Choi, Younga - Closed - 800410 - 0",
                    "destino_id": "choi-nuevo",
                    "destino_nombre": "Choi, Younga T. - 800012 - 2-25-cv-00985",
                    "subcarpeta": ["00_Unfiled", "Fusionado de 800410 - 0"],
                    "eliminar_origen": True,
                },
            ),
            Accion(
                RENOMBRAR, "4_index_desde_ocr", "prueba",
                {
                    "carpeta_id": "1738",
                    "nombre_actual": "1738 East 4th Street LLC - 200026 - 0",
                    "nombre_nuevo": "1738 East 4th Street LLC - 200026 - 1-23-cv-01270",
                },
            ),
        ]
    )  # fmt: skip


def test_simular_no_cambia_nada(tmp_path):
    sp = SharePointEnMemoria()
    antes = sp.estado()
    resultado = Ejecutor(sp, Diario(tmp_path / "d.jsonl"), simular=True).aplicar(_plan())
    assert sp.estado() == antes
    assert len(resultado.hechas) == 2  # noqa: PLR2004
    assert not (tmp_path / "d.jsonl").exists()


def test_aplicar_fusiona_sin_dejar_la_carpeta_vieja_y_deshacer_la_recupera(tmp_path):
    sp = SharePointEnMemoria()
    nombres_antes = {d["name"]: _ruta(sp, i) for i, d in sp.items.items()}
    diario = Diario(tmp_path / "d.jsonl")

    resultado = Ejecutor(sp, diario, simular=False).aplicar(_plan())
    assert resultado.error is None and len(resultado.hechas) == 2  # noqa: PLR2004
    assert "choi-viejo" not in sp.items  # la carpeta vieja ya no existe
    destino = next(i for i, d in sp.items.items() if d["name"] == "Fusionado de 800410 - 0")
    for archivo in ("complaint", "discovery", "jsonl"):  # todo se movió, el JSONL también
        assert sp.items[archivo]["padre"] == destino
    assert sp.items["1738"]["name"].endswith("1-23-cv-01270")

    deshacer(sp, diario.ruta, simular=False)
    nombres_despues = {d["name"]: _ruta(sp, i) for i, d in sp.items.items()}
    assert nombres_despues == nombres_antes  # misma estructura, sin carpetas de más


def _ruta(sp, item_id):
    partes = []
    while item_id:
        partes.append(sp.items[item_id]["name"])
        item_id = sp.items[item_id]["padre"]
    return "/".join(reversed(partes))


def test_no_elimina_si_la_carpeta_vieja_no_quedo_vacia(tmp_path):
    sp = SharePointEnMemoria()
    original = sp.mover
    sp.mover = lambda item_id, padre: None if item_id == "complaint" else original(item_id, padre)
    resultado = Ejecutor(sp, Diario(tmp_path / "d.jsonl"), simular=False).aplicar(_plan())
    assert "choi-viejo" in sp.items
    assert resultado.error and "no quedó vacía" in resultado.error


def test_plan_desactualizado_se_salta(tmp_path):
    sp = SharePointEnMemoria()
    sp.renombrar("1738", "Alguien la renombró")
    resultado = Ejecutor(sp, Diario(tmp_path / "d.jsonl"), simular=False).aplicar(_plan())
    assert len(resultado.saltadas) == 1
    assert sp.items["1738"]["name"] == "Alguien la renombró"
