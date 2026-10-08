"""El reporte de un plan para Mario, clasificado según la guía de revisión de calidad.

La guía manda: el index identifica el caso; fusionar, crear carpetas o elegir entre varias
candidatas es "para y pregunta"; una acción previa citada o un anexo no es un error; un
index adivinado es peor que uno faltante. Este reporte reparte cada hallazgo del plan en
esas categorías y dice a quién le toca.

Privacidad (guía, "El JSONL tiene datos personales"): el reporte solo cita conclusiones
(nombres de carpeta, index, nombres de archivo y conteos), nunca texto de los documentos.
"""

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from app.revision.nombres import leer_nombre
from app.revision.plan import FUSIONAR, RENOMBRAR, Accion, Hallazgo, Plan

ANIO_MAXIMO_RAZONABLE = 2027
MINIMO_DOCS_CASO_SIN_CARPETA = 3
NOMBRE_DE_NYSCEF = re.compile(r"^(\d{3,7})_((?:19|20)\d{2})_")
# "Ex. A - Transcript", "Amshen Aff Ex. A - ...", "Exhibit 3", "Exh B": anexos.
ANEXO = re.compile(r"\b(ex\.?\s?[a-z0-9]{1,3}\b|exh\b|exhibit)", re.IGNORECASE)
LIMITE_EJEMPLOS = 12


@dataclass
class Clasificacion:
    aplicar: list[Accion] = field(default_factory=list)
    fusiones: list[Accion] = field(default_factory=list)
    plantillas: list[Hallazgo] = field(default_factory=list)
    mover: list[Hallazgo] = field(default_factory=list)
    casos_sin_carpeta: list[Hallazgo] = field(default_factory=list)
    mezcladas: list[Hallazgo] = field(default_factory=list)
    sin_index_varios: list[Hallazgo] = field(default_factory=list)
    preguntar: list[Hallazgo] = field(default_factory=list)
    referencias: list[Hallazgo] = field(default_factory=list)
    anexos: list[Hallazgo] = field(default_factory=list)
    ruido: list[Hallazgo] = field(default_factory=list)


def _es_anexo(h: Hallazgo) -> bool:
    return bool(ANEXO.search(h.datos.get("file_name", "")))


def _es_descarga_del_otro_caso(h: Hallazgo) -> bool:
    coincide = NOMBRE_DE_NYSCEF.match(h.datos.get("file_name", ""))
    otro = h.datos.get("found_index", "")
    return bool(coincide) and f"{int(coincide.group(1))}/{coincide.group(2)}" == otro


def _un_digito(index: str, propio: str | None) -> bool:
    if not propio or "/" not in index or "/" not in propio:
        return False
    (numero, anio), (numero_propio, anio_propio) = index.split("/"), propio.split("/")
    if anio != anio_propio or len(numero) != len(numero_propio):
        return False
    return sum(a != b for a, b in zip(numero, numero_propio, strict=True)) == 1


def _es_ruido(h: Hallazgo) -> bool:
    index = h.datos.get("index", "")
    anio = int(index.rsplit("/", 1)[-1]) if "/" in index else 0
    pocos = len(h.datos.get("documentos", [])) < MINIMO_DOCS_CASO_SIN_CARPETA
    return anio > ANIO_MAXIMO_RAZONABLE or _un_digito(index, leer_nombre(h.carpeta).index) or pocos


def _clasificar_hallazgo(c: Clasificacion, h: Hallazgo) -> None:
    regla = h.regla
    if regla == "8_index_equivocado_en_documento":
        c.plantillas.append(h)
    elif regla == "4_documento_de_otro_caso_del_cliente":
        (c.mover if _es_descarga_del_otro_caso(h) else c.referencias).append(h)
    elif regla == "4_documento_de_otro_cliente":
        (c.anexos if _es_anexo(h) else c.mover).append(h)
    elif regla == "6_index_sin_carpeta":
        (c.ruido if _es_ruido(h) else c.casos_sin_carpeta).append(h)
    elif regla == "6_varios_casos":
        c.mezcladas.append(h)
    elif regla == "6_varios_index":
        c.sin_index_varios.append(h)
    elif not regla.endswith(("_seguimiento", "_hubspot", "_informativo")):
        c.preguntar.append(h)


def clasificar(plan: Plan) -> Clasificacion:
    c = Clasificacion()
    for accion in plan.acciones:
        (c.fusiones if accion.tipo == FUSIONAR else c.aplicar).append(accion)
    for hallazgo in plan.hallazgos:
        _clasificar_hallazgo(c, hallazgo)
    return c


# ---------------------------------------------------------------------------- texto


def _tipo(nombre: str) -> str:
    return (leer_nombre(nombre).id_interno or "?")[0]


def _seccion(titulo: str, lineas: list[str], nota: str = "") -> list[str]:
    salida = ["", f"## {titulo}", ""]
    if nota:
        salida += [nota, ""]
    return salida + (lineas or ["_Ninguno en este plan._"])


def _tabla_renombres(acciones: list[Accion]) -> list[str]:
    filas = [a for a in acciones if a.tipo == RENOMBRAR]
    lineas = ["| Carpeta | Nuevo nombre | Evidencia |", "|---|---|---|"]
    lineas += [
        f"| {a.datos['nombre_actual']} | {a.datos['nombre_nuevo']} | {a.motivo} |" for a in filas
    ]
    return lineas if filas else []


def _tabla_fusiones(acciones: list[Accion]) -> list[str]:
    lineas = [
        "| Carpeta sin index o cerrada | Carpeta destino | Evidencia | Aviso |",
        "|---|---|---|---|",
    ]
    for a in acciones:
        d = a.datos
        aviso = (
            f"Tipos de caso distintos ({_tipo(d['origen_nombre'])} y {_tipo(d['destino_nombre'])})"
            if _tipo(d["origen_nombre"]) != _tipo(d["destino_nombre"])
            else ""
        )
        lineas.append(f"| {d['origen_nombre']} | {d['destino_nombre']} | {a.motivo} | {aviso} |")
    return lineas if acciones else []


def _tabla_documentos(hallazgos: list[Hallazgo], columna: str) -> list[str]:
    lineas = [
        f"| Carpeta | Documento | Index del documento | {columna} | Copias |",
        "|---|---|---|---|---|",
    ]
    # El mismo archivo puede estar en dos subcarpetas: una fila por archivo, con sus copias.
    filas = Counter(
        (h.carpeta, h.datos.get("file_name", ""), h.datos.get("found_index", ""),
         h.datos.get("found_index_belongs_to", ""))
        for h in hallazgos
    )  # fmt: skip
    for (carpeta, archivo, index, destino), copias in filas.items():
        lineas.append(f"| {carpeta} | {archivo} | {index} | {destino} | {copias} |")
    return lineas if hallazgos else []


def _tabla_index(hallazgos: list[Hallazgo]) -> list[str]:
    lineas = ["| Carpeta | Index sin carpeta | Documentos | Ejemplo |", "|---|---|---|---|"]
    for h in sorted(hallazgos, key=lambda x: -len(x.datos.get("documentos", []))):
        docs = h.datos.get("documentos", [])
        ejemplo = docs[0] if docs else ""
        lineas.append(f"| {h.carpeta} | {h.datos.get('index', '')} | {len(docs)} | {ejemplo} |")
    return lineas if hallazgos else []


def _lista(hallazgos: list[Hallazgo]) -> list[str]:
    por_carpeta = defaultdict(list)
    for h in hallazgos:
        por_carpeta[h.carpeta].append(h)
    lineas = []
    for carpeta, grupo in sorted(por_carpeta.items()):
        lineas.append(f"- **{carpeta}**: {grupo[0].headline}")
        conteo = grupo[0].datos.get("index_en_documentos") or {}
        if conteo:
            ordenados = sorted(conteo.items(), key=lambda x: -x[1])
            lineas.append(
                "  - Index en sus documentos (documentos): "
                + ", ".join(f"`{index}` ({n})" for index, n in ordenados)
            )
    return lineas


def _relaciones(hallazgos: list[Hallazgo]) -> list[str]:
    pares = Counter((h.carpeta, h.datos.get("found_index_belongs_to", "")) for h in hallazgos)
    lineas = ["| Carpeta | Cita otro caso del mismo cliente | Documentos |", "|---|---|---|"]
    lineas += [f"| {a} | {b} | {n} |" for (a, b), n in pares.most_common(LIMITE_EJEMPLOS)]
    resto = len(pares) - LIMITE_EJEMPLOS
    if resto > 0:
        lineas.append(f"| … y {resto} parejas más | | |")
    return lineas if hallazgos else []


def _matter_context(c: Clasificacion) -> list[str]:
    clientes = defaultdict(set)
    for h in c.referencias:
        destino = h.datos.get("found_index_belongs_to", "")
        clientes[leer_nombre(h.carpeta).cliente].update({h.carpeta, destino})
    lineas = [
        f"- **{cliente}**: {len(carpetas)} carpetas que se citan entre sí "
        f"({'; '.join(sorted(carpetas))}). Las citas cruzadas son normales; no es un conflicto."
        for cliente, carpetas in sorted(clientes.items(), key=lambda x: -len(x[1]))
        if len(carpetas) > 2  # noqa: PLR2004
    ]
    if c.mezcladas:
        lineas.append(
            f"- Las {len(c.mezcladas)} carpetas con varios casos de la sección 3: cuáles son "
            "los casos, cuál está vivo y dónde vive cada uno."
        )
    return lineas


def generar_reporte(plan: Plan, nombre_plan: str) -> str:
    c = clasificar(plan)
    resumen = [
        "| Clasificación (guía) | Cantidad | Quién |",
        "|---|---|---|",
        f"| Aplicar (renombres con evidencia) | {len(c.aplicar)} | RevOps + HubSpot |",
        f"| Fusiones propuestas: para y pregunta | {len(c.fusiones)} | **Mario** |",
        f"| Posibles casos sin carpeta: para y pregunta | {len(c.casos_sin_carpeta)} | **Mario** |",
        f"| Carpetas con varios casos | {len(c.mezcladas)} | **Mario** / abogado |",
        f"| Carpetas sin index con varios index | {len(c.sin_index_varios)} | **Mario** |",
        f"| Otros para y pregunta | {len(c.preguntar)} | **Mario** |",
        f"| Documentos con el index de otro cliente (plantilla) | {len(c.plantillas)} "
        "| Abogado del caso |",
        f"| Posibles documentos mal archivados (mover) | {len(c.mover)} | Revisar y mover |",
        f"| Referencias a otro caso del mismo cliente | {len(c.referencias)} | No tocar |",
        f"| Anexos (Exhibits) | {len(c.anexos)} | No tocar |",
        f"| Ruido del OCR | {len(c.ruido)} | Ignorar |",
    ]
    partes = [
        f"# Reporte para Mario — {nombre_plan}",
        "",
        f"Plan generado el {plan.generado} con las reglas `{plan.reglas or 'sin versión'}`. "
        "**Nada de esto se ha aplicado.** Clasificado según la guía de revisión de calidad.",
        "",
        "> Este reporte solo cita conclusiones: nombres de carpeta, index y nombres de archivo. "
        "No contiene texto de los documentos. Queda en `salida/revision/` de este equipo; "
        "no lo copies a correo, chat ni herramientas externas.",
        "",
        "## Resumen",
        "",
        *resumen,
    ]
    partes += _seccion(
        "1. Para y pregunta: fusiones propuestas",
        _tabla_fusiones(c.fusiones),
        "La guía: fusionar es destructivo. Ninguna se aplica sin tu visto bueno.",
    )
    partes += _seccion(
        "2. Para y pregunta: posibles casos sin carpeta",
        _tabla_index(c.casos_sin_carpeta),
        "Muchos documentos con un index que no tiene carpeta en Matters. Crear la carpeta "
        "implica asignar un ID interno.",
    )
    partes += _seccion(
        "3. Carpetas con varios casos mezclados",
        _lista(c.mezcladas),
        "Según la guía: una subcarpeta por index, un `_READ ME FIRST.md` y una línea "
        "`matter_context`. No mover documentos sueltos.",
    )
    partes += _seccion(
        "4. Carpetas sin index cuyos documentos traen varios index",
        _lista(c.sin_index_varios),
        "Un index adivinado es peor que uno faltante: no se renombran.",
    )
    partes += _seccion("5. Otros para y pregunta", _lista(c.preguntar))
    partes += _seccion(
        "6. Renombres con evidencia (listos para aplicar)",
        _tabla_renombres(c.aplicar),
        "Al aplicarlos hay que poner el mismo index en `index_number` del Matter en HubSpot.",
    )
    partes += _seccion(
        "7. Documentos con el index de otro cliente (para el abogado del caso)",
        _tabla_documentos(c.plantillas, "Ese index es de"),
        "El documento es de este cliente, pero lleva el index de otro caso: plantilla mal "
        "editada. Verificar si alguno ya se radicó así.",
    )
    partes += _seccion(
        "8. Posibles documentos mal archivados",
        _tabla_documentos(c.mover, "Carpeta del otro caso"),
        "Si la carátula del documento es de ese otro caso, va al `00_Unfiled` de esa carpeta.",
    )
    partes += _seccion(
        "9. No tocar: referencias entre casos del mismo cliente",
        _relaciones(c.referencias),
        "Acciones previas y Article 15 que citan su foreclosure: es normal (guía, sección 3).",
    )
    partes += _seccion(
        "10. `matter_context` sugeridos",
        _matter_context(c),
        "Para que nadie vuelva a investigar lo mismo (guía, sección 5).",
    )
    partes += [
        "",
        "## 11. No tocar ni revisar",
        "",
        f"- {len(c.anexos)} anexos (archivos `Ex.`/`Exhibit`) que citan otro caso a propósito.",
        f"- {len(c.ruido)} index que son ruido del OCR (año imposible, un dígito cambiado o "
        "citas en 1 o 2 documentos).",
    ]
    return "\n".join(partes) + "\n"
