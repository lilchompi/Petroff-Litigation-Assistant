"""Vigilancia de los JSONL que van llegando a SharePoint.

Lleva en salida/revision/jsonl_revisados.json qué JSONL ya entraron en un plan (por su id
de SharePoint y la fecha en que se modificó). Un JSONL es "nuevo" si no está en ese
registro, o si se volvió a generar después (cambió su fecha de modificación).
"""

import json
from dataclasses import dataclass
from pathlib import Path

from app.core.config import settings
from app.sharepoint import ClienteGraph

CODIFICACION = "utf-8"


@dataclass(frozen=True)
class JsonlRemoto:
    id: str
    carpeta: str
    nombre: str
    modificado: str  # lastModifiedDateTime de SharePoint (ISO, UTC)


def listar_jsonl(cliente: ClienteGraph, carpetas: list[str]) -> list[JsonlRemoto]:
    return [
        JsonlRemoto(item["id"], carpeta, item["name"], item.get("lastModifiedDateTime", ""))
        for carpeta in carpetas
        for item in cliente.hijos_de_ruta(carpeta)
        if "folder" not in item and item["name"].casefold().endswith(".jsonl")
    ]


class Registro:
    def __init__(self, ruta: Path | None = None) -> None:
        self.ruta = ruta or settings.REVISION_DIR / "jsonl_revisados.json"
        self.revisados: dict[str, str] = {}
        if self.ruta.exists():
            self.revisados = json.loads(self.ruta.read_text(encoding=CODIFICACION))

    def nuevos(self, remotos: list[JsonlRemoto]) -> list[JsonlRemoto]:
        return [r for r in remotos if self.revisados.get(r.id) != r.modificado]

    def marcar(self, remotos: list[JsonlRemoto]) -> None:
        self.revisados.update({r.id: r.modificado for r in remotos})
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        self.ruta.write_text(json.dumps(self.revisados, indent=1), encoding=CODIFICACION)
