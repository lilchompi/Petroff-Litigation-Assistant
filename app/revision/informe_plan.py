"""El plan de revisión como texto legible para una persona."""

from collections import defaultdict

from app.revision.plan import FUSIONAR, RENOMBRAR, Hallazgo, Plan

TITULOS_HALLAZGOS = [
    (
        "8_index_equivocado_en_documento",
        "DOCUMENTOS CON EL INDEX DE OTRO CASO (corregir antes de radicar)",
    ),
    ("4_index_sugerido", "INDEX SUGERIDOS (un solo documento: falta confirmarlo)"),
    ("3_nombre_carpeta", "NOMBRES DE CARPETA CON ERRORES"),
    ("5_id_repetido", "ID INTERNO REPETIDO"),
    ("6_index_en_varias_carpetas", "INDEX QUE ESTÁ EN VARIAS CARPETAS"),
    ("7_mismo_index", "MISMO INDEX Y MISMO NOMBRE, SIN CONFIRMAR"),
]


def _acciones(plan: Plan) -> list[str]:
    renombrar = [a for a in plan.acciones if a.tipo == RENOMBRAR]
    fusionar = [a for a in plan.acciones if a.tipo == FUSIONAR]
    lineas = ["", f"RENOMBRAR CARPETAS ({len(renombrar)}):"]
    for a in renombrar:
        lineas += [
            f"  - {a.datos['nombre_actual']}",
            f"      -> {a.datos['nombre_nuevo']}",
            f"      ({a.motivo})",
        ]
    lineas += ["", f"FUSIONAR CARPETAS ({len(fusionar)}):"]
    for a in fusionar:
        lineas += [
            f"  - {a.datos['origen_nombre']}",
            f"      -> dentro de {a.datos['destino_nombre']}/{'/'.join(a.datos['subcarpeta'])}",
            f"      ({a.regla}: {a.motivo})",
            "      (después se elimina la carpeta vieja, ya vacía)",
        ]
    return lineas


def _hallazgos(titulo: str, hallazgos: list[Hallazgo]) -> list[str]:
    if not hallazgos:
        return []
    lineas = ["", f"{titulo} ({len(hallazgos)}):"]
    for h in hallazgos:
        archivo = f" [{h.datos['file_name']}]" if h.datos.get("file_name") else ""
        lineas.append(f"  - {h.carpeta}{archivo}: {h.headline}")
    return lineas


def informe_plan(plan: Plan, encabezado: list[str]) -> str:
    por_regla: dict[str, list[Hallazgo]] = defaultdict(list)
    para_llm = []
    for h in plan.hallazgos:
        (para_llm if h.para_llm else por_regla[h.regla]).append(h)
    lineas = [*encabezado, *_acciones(plan)]
    for regla, titulo in TITULOS_HALLAZGOS:
        lineas += _hallazgos(titulo, por_regla.get(regla, []))
    seguimiento = [
        h for r, hs in por_regla.items() if r.endswith(("_seguimiento", "_hubspot")) for h in hs
    ]
    lineas += _hallazgos("SEGUIMIENTO (HubSpot y JSONL)", seguimiento)
    lineas += _hallazgos("PENDIENTES PARA EL LLM O UNA PERSONA (no se decidió nada)", para_llm)
    return "\n".join(lineas)
