"""El plan que produce la revisión: acciones a ejecutar y hallazgos a informar.

- Acción: algo que el ejecutor hará en SharePoint (renombrar o fusionar carpetas).
- Hallazgo: algo que se informa y se deja escrito como línea `review_finding`, para quien
  revise después (o para el LLM, si `para_llm`). No cambia nada en SharePoint.
"""

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

RENOMBRAR = "renombrar"
FUSIONAR = "fusionar"
ESCRITO_POR = "Revision de calidad RevOps"
CODIFICACION = "utf-8"


def ahora() -> str:
    return datetime.now().isoformat(timespec="seconds")


@dataclass
class Accion:
    tipo: str  # RENOMBRAR | FUSIONAR
    regla: str
    motivo: str
    # renombrar: carpeta_id, nombre_actual, nombre_nuevo
    # fusionar: origen_id, origen_nombre, destino_id, destino_nombre, subcarpeta
    datos: dict[str, Any]
    evidencia: dict[str, Any] = field(default_factory=dict)


@dataclass
class Hallazgo:
    regla: str
    headline: str
    carpeta: str
    datos: dict[str, Any] = field(default_factory=dict)
    para_llm: bool = False

    def como_review_finding(self) -> dict[str, Any]:
        """La línea que se añade al JSONL del caso (formato acordado)."""
        return {
            "record_type": "review_finding",
            "generated": ahora(),
            "written_by": ESCRITO_POR,
            "rule": self.regla,
            "matter_folder": self.carpeta,
            "headline": self.headline,
            "needs_llm": self.para_llm,
            "status": "pendiente",
            **self.datos,
        }


@dataclass
class Plan:
    generado: str = field(default_factory=ahora)
    reglas: str = ""  # versión de config/reglas_revision.toml con que se generó
    acciones: list[Accion] = field(default_factory=list)
    hallazgos: list[Hallazgo] = field(default_factory=list)

    def a_dict(self) -> dict[str, Any]:
        return {
            "generado": self.generado,
            "reglas": self.reglas,
            "acciones": [asdict(a) for a in self.acciones],
            "hallazgos": [asdict(h) for h in self.hallazgos],
        }

    def guardar(self, ruta: Path) -> None:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(
            json.dumps(self.a_dict(), ensure_ascii=False, indent=2), encoding=CODIFICACION
        )

    @classmethod
    def cargar(cls, ruta: Path) -> "Plan":
        datos = json.loads(ruta.read_text(encoding=CODIFICACION))
        return cls(
            generado=datos["generado"],
            reglas=datos.get("reglas", ""),
            acciones=[Accion(**a) for a in datos["acciones"]],
            hallazgos=[Hallazgo(**h) for h in datos["hallazgos"]],
        )
