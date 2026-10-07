"""Las reglas de revisión que no necesitan LLM. Solo leen y llenan un Plan.

Reglas (ver salida/REGLAS_REVISION_MATTERS.md):
- 2 Ruido: rangos de años, fragmentos del index propio, citas comunes.
- 3 Nombre de carpeta con errores.
- 4 Carpeta '- 0' con un único index en el OCR y sin otra carpeta con ese index: se
    renombra con 2 o más documentos; con 1, se sugiere.
- 5 Fusión: mismo ID interno + mismo nombre.
- 6 Fusión: carpeta '- 0', el OCR trae el index de otra carpeta, sin otro index, mismo nombre.
- 7 Fusión: mismo index + mismo nombre + el OCR de la carpeta lo confirma.
- 8 Documento del cliente con el index de otro caso: se informa, no se toca.
Lo ambiguo (otros clientes, varios casos en una carpeta) se informa con para_llm=True.
"""

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date

from app.revision.indices import es_fragmento_de
from app.revision.nombres import (
    SEPARADOR,
    NombreCarpeta,
    index_para_nombre,
    leer_nombre,
    mismo_nombre,
    nombre_menciona_cliente,
)
from app.revision.plan import FUSIONAR, RENOMBRAR, Accion, Hallazgo, Plan
from app.revision.reglas import Reglas
from app.validacion.inventario_jsonl import ArchivoJsonl

# Así nombra NYSCEF los documentos que se descargan: "710731_2015_Deutsche_v_...".
NOMBRE_DE_NYSCEF = re.compile(r"^(\d{3,7})_((?:19|20)\d{2})_")


@dataclass(frozen=True)
class Carpeta:
    id: str
    nombre: NombreCarpeta

    @property
    def titulo(self) -> str:
        return self.nombre.original


class IndiceMatters:
    """Las carpetas de caso de Matters/, buscables por index y por ID interno."""

    def __init__(self, carpetas: dict[str, str]) -> None:
        self.por_index: dict[str, list[Carpeta]] = defaultdict(list)
        self.por_id_interno: dict[str, list[Carpeta]] = defaultdict(list)
        self.por_item: dict[str, Carpeta] = {}
        for titulo, item_id in carpetas.items():
            carpeta = Carpeta(item_id, leer_nombre(titulo))
            self.por_item[item_id] = carpeta
            if carpeta.nombre.index:
                self.por_index[carpeta.nombre.index].append(carpeta)
            if carpeta.nombre.id_interno:
                self.por_id_interno[carpeta.nombre.id_interno].append(carpeta)

    def con_index(self, index: str, salvo: Carpeta) -> list[Carpeta]:
        return [c for c in self.por_index.get(index, []) if c.id != salvo.id]

    def con_id_interno(self, carpeta: Carpeta) -> list[Carpeta]:
        id_interno = carpeta.nombre.id_interno
        return [c for c in self.por_id_interno.get(id_interno or "", []) if c.id != carpeta.id]


@dataclass
class Revision:
    """Estado de la revisión de un lote: el plan y las carpetas que ya tienen una acción."""

    matters: IndiceMatters
    citas: set[str] = field(default_factory=set)
    reglas: Reglas = field(default_factory=Reglas)
    plan: Plan = field(default_factory=Plan)
    comprometidas: set[str] = field(default_factory=set)
    # Renombres de la regla 4: se confirman en cerrar(), cuando se conoce todo el lote.
    renombres: dict[str, list[tuple[Carpeta, int]]] = field(default_factory=dict)

    # ------------------------------------------------------------------ acciones

    def _hallazgo(self, regla: str, carpeta: Carpeta, headline: str, **datos) -> None:
        para_llm = bool(datos.pop("para_llm", False))
        self.plan.hallazgos.append(Hallazgo(regla, headline, carpeta.titulo, datos, para_llm))

    def _renombrar(self, carpeta: Carpeta, index: str, documentos: int) -> None:
        self.renombres.setdefault(index, []).append((carpeta, documentos))
        self.comprometidas.add(carpeta.id)

    def cerrar(self) -> Plan:
        """Confirma los renombres. Si varias carpetas sin index apuntan al mismo index, no
        se renombra ninguna: ¿es un caso o son varios? (Hernandez, Nelson ×3)."""
        for index, carpetas in self.renombres.items():
            if len(carpetas) == 1:
                self._confirmar_renombre(*carpetas[0], index)
                continue
            self._hallazgo(
                "7_cliente_en_varias_carpetas",
                carpetas[0][0],
                f"{len(carpetas)} carpetas sin index citan {index}: ¿es un caso o son varios?",
                carpetas=[c.titulo for c, _ in carpetas],
                index=index,
                para_llm=True,
            )
        self.renombres = {}
        return self.plan

    def _confirmar_renombre(self, carpeta: Carpeta, documentos: int, index: str) -> None:
        base = carpeta.titulo.rsplit(SEPARADOR, 1)[0]
        nuevo = f"{base}{SEPARADOR}{index_para_nombre(index)}"
        self.plan.acciones.append(
            Accion(
                RENOMBRAR,
                "4_index_desde_ocr",
                f"{documentos} documentos de corte llevan {index} y ninguna otra carpeta lo tiene",
                {"carpeta_id": carpeta.id, "nombre_actual": carpeta.titulo, "nombre_nuevo": nuevo},
                {"index": index, "documentos": documentos},
            )
        )
        self._hallazgo(
            "4_actualizar_hubspot",
            carpeta,
            f"Carpeta renombrada con el index {index}: actualizar index_number del Matter "
            "en HubSpot.",
            index=index,
        )

    def _fusionar(
        self, origen: Carpeta, destino: Carpeta, regla: str, motivo: str, **evidencia
    ) -> None:
        if {origen.id, destino.id} & self.comprometidas:
            return  # ya hay una acción sobre alguna de las dos (p. ej. desde el otro JSONL)
        subcarpeta = f"Fusionado de {origen.nombre.id_interno} - {origen.nombre.index_tal_cual}"
        self.plan.acciones.append(
            Accion(
                FUSIONAR,
                regla,
                motivo,
                {
                    "origen_id": origen.id,
                    "origen_nombre": origen.titulo,
                    "destino_id": destino.id,
                    "destino_nombre": destino.titulo,
                    "subcarpeta": [self.reglas.subcarpeta_fusion, subcarpeta],
                    "eliminar_origen": True,
                },
                evidencia,
            )
        )
        self.comprometidas |= {origen.id, destino.id}
        self._hallazgo(
            f"{regla}_seguimiento",
            destino,
            f"Se fusionó '{origen.titulo}' aquí: dejar un solo Matter en HubSpot y pasar las "
            "líneas de su JSONL a este caso.",
            origen=origen.titulo,
        )

    # ------------------------------------------------------------------ reglas

    def _indices(self, carpeta: Carpeta, archivos: list[ArchivoJsonl]) -> dict[str, list]:
        """{index: documentos con ese index en la carátula}, ya sin ruido (regla 2)."""
        propio = carpeta.nombre.index
        documentos: dict[str, list[ArchivoJsonl]] = defaultdict(list)
        for archivo in archivos:
            for index in archivo.indices_caratula:
                if not self._es_ruido(index, propio):
                    documentos[index].append(archivo)
        return dict(documentos)

    def _es_ruido(self, index: str, propio: str | None) -> bool:
        if index in self.citas or es_fragmento_de(index, propio):
            return True
        anio = int(index.rsplit("/", 1)[-1]) if "/" in index else None
        limite = self.reglas.anios_en_el_futuro
        if limite and anio and anio > date.today().year + limite:
            return True
        return self.reglas.un_digito_distinto_es_ocr and _un_digito_distinto(index, propio)

    def _mismo_nombre(self, a: NombreCarpeta, b: NombreCarpeta) -> bool:
        if mismo_nombre(a, b):
            return True
        return any({a.cliente, b.cliente} <= grupo for grupo in self.reglas.alias)

    def _nombre(self, carpeta: Carpeta) -> None:
        for problema in carpeta.nombre.problemas:
            self._hallazgo("3_nombre_carpeta", carpeta, f"El nombre {problema}.")

    def _mismo_id(self, carpeta: Carpeta) -> None:
        """Regla 5: mismo ID interno + mismo nombre."""
        for otra in self.matters.con_id_interno(carpeta):
            if not self._mismo_nombre(carpeta.nombre, otra.nombre):
                self._hallazgo(
                    "5_id_repetido",
                    carpeta,
                    f"El ID {carpeta.nombre.id_interno} también está en '{otra.titulo}', de otro "
                    "cliente: un ID no debería repetirse.",
                    otra_carpeta=otra.titulo,
                )
                continue
            pareja = _orientar(carpeta, otra)
            if pareja is None:
                self._hallazgo(
                    "5_id_repetido",
                    carpeta,
                    f"Mismo ID y mismo nombre que '{otra.titulo}', pero no se sabe cuál conservar.",
                    otra_carpeta=otra.titulo,
                    para_llm=True,
                )
                continue
            self._fusionar(*pareja, "5_mismo_id_mismo_nombre", "Mismo ID interno y mismo cliente")

    def _sin_index(self, carpeta: Carpeta, indices: dict[str, list]) -> None:
        """Reglas 4 y 6, para una carpeta que termina en '- 0'."""
        if len(indices) > 1:
            self._hallazgo(
                "6_varios_index",
                carpeta,
                "La carpeta no tiene index y sus documentos traen varios distintos.",
                index_en_documentos={i: len(d) for i, d in indices.items()},
                para_llm=True,
            )
            return
        index, documentos = next(iter(indices.items()))
        destinos = self.matters.con_index(index, carpeta)
        if not destinos:
            self._sin_destino(carpeta, index, len(documentos))
        elif len(destinos) > 1:
            self._hallazgo(
                "6_index_en_varias_carpetas",
                carpeta,
                f"Sus documentos llevan {index}, que está en varias carpetas: no se escoge "
                "ninguna.",
                candidatas=[d.titulo for d in destinos],
            )
        elif self._mismo_nombre(carpeta.nombre, destinos[0].nombre):
            self._fusionar(
                carpeta,
                destinos[0],
                "6_ocr_confirma_index",
                f"{len(documentos)} documento(s) llevan {index}, el index de la otra carpeta",
                index=index,
                documentos=[d.nombre for d in documentos],
            )
        else:
            self._documentos_de_otro(carpeta, destinos[0], index, documentos)

    def _sin_destino(self, carpeta: Carpeta, index: str, documentos: int) -> None:
        if documentos >= self.reglas.minimo_documentos_para_renombrar:
            self._renombrar(carpeta, index, documentos)
        else:
            self._hallazgo(
                "4_index_sugerido",
                carpeta,
                f"Un documento lleva {index}: posible index de la carpeta (falta confirmarlo).",
                index=index,
            )

    def _con_index(self, carpeta: Carpeta, indices: dict[str, list]) -> None:
        """Regla 7 y los index ajenos de una carpeta que sí tiene index."""
        propio = carpeta.nombre.index
        for otra in self.matters.con_index(propio, carpeta):
            self._mismo_index(carpeta, otra, len(indices.get(propio, [])))
        ajenos = {i: d for i, d in indices.items() if i != propio}
        if ajenos and max(len(d) for d in ajenos.values()) > len(indices.get(propio, [])):
            self._hallazgo(
                "6_varios_casos",
                carpeta,
                "Hay más documentos con otro index que con el de la carpeta: varios casos "
                "mezclados, o el index del nombre está equivocado.",
                index_en_documentos={i: len(d) for i, d in indices.items()},
                para_llm=True,
            )
            return
        for index, documentos in ajenos.items():
            destinos = self.matters.con_index(index, carpeta)
            if destinos:
                self._documentos_de_otro(carpeta, destinos[0], index, documentos)
            elif len(documentos) < self.reglas.index_sin_carpeta_minimo_documentos:
                self._hallazgo(
                    "6_index_sin_carpeta_informativo",
                    carpeta,
                    f"{len(documentos)} documento(s) citan {index}, que no tiene carpeta "
                    "(probable cita o acción previa).",
                    index=index,
                    documentos=[d.nombre for d in documentos],
                )
            else:
                self._hallazgo(
                    "6_index_sin_carpeta",
                    carpeta,
                    f"{len(documentos)} documento(s) llevan {index}, que no tiene carpeta.",
                    index=index,
                    documentos=[d.nombre for d in documentos],
                    para_llm=True,
                )

    def _mismo_index(self, carpeta: Carpeta, otra: Carpeta, confirmados: int) -> None:
        if not self._mismo_nombre(carpeta.nombre, otra.nombre):
            self._hallazgo(
                "7_mismo_index_otro_cliente",
                carpeta,
                f"'{otra.titulo}' tiene el mismo index: probablemente codemandados en el "
                "mismo pleito.",
                otra_carpeta=otra.titulo,
                para_llm=True,
            )
            return
        pareja = _orientar(carpeta, otra)
        if not confirmados or pareja is None:
            self._hallazgo(
                "7_mismo_index",
                carpeta,
                f"Mismo index y mismo nombre que '{otra.titulo}', pero el OCR no lo confirma o no "
                "se sabe cuál conservar.",
                otra_carpeta=otra.titulo,
            )
            return
        self._fusionar(
            *pareja,
            "7_mismo_index_mismo_nombre",
            f"Mismo index y mismo cliente; {confirmados} documento(s) lo confirman",
        )

    def _documentos_de_otro(
        self, carpeta: Carpeta, destino: Carpeta, index: str, documentos: list[ArchivoJsonl]
    ) -> None:
        """Regla 8 si el archivo es del cliente y el index de otro cliente; si no, al LLM."""
        mismo_cliente = self._mismo_nombre(carpeta.nombre, destino.nombre)
        for documento in documentos:
            propio = not mismo_cliente and nombre_menciona_cliente(documento.nombre, carpeta.nombre)
            regla, headline = _tipo_de_documento_ajeno(mismo_cliente, propio, index, destino)
            informativo = (
                mismo_cliente
                and self.reglas.mismo_cliente_otro_caso_es_informativo
                and not _es_descarga_de_nyscef(documento.nombre, index)
            )
            if informativo:
                regla = "4_relacion_entre_casos_informativo"
                headline = f"Cita {index}, otro caso del mismo cliente ('{destino.titulo}')."
            self._hallazgo(
                regla,
                carpeta,
                headline,
                sharepoint_id=documento.id,
                file_name=documento.nombre,
                subfolder=documento.carpeta,
                found_index=index,
                found_index_belongs_to=destino.titulo,
                expected_index=carpeta.nombre.index,
                para_llm=not propio and not informativo,
            )

    # ------------------------------------------------------------------ entrada

    def revisar(self, carpeta_id: str, archivos: list[ArchivoJsonl]) -> None:
        carpeta = self.matters.por_item.get(carpeta_id)
        if carpeta is None:
            return
        self._nombre(carpeta)
        self._mismo_id(carpeta)
        indices = self._indices(carpeta, archivos)
        if carpeta.id in self.comprometidas or not indices:
            return
        if carpeta.nombre.sin_index:
            self._sin_index(carpeta, indices)
        elif carpeta.nombre.index:
            self._con_index(carpeta, indices)


def _un_digito_distinto(index: str, propio: str | None) -> bool:
    """726562/2022 frente a 725562/2022: el OCR leyó mal un dígito del index propio."""
    if not propio or "/" not in index or "/" not in propio:
        return False
    (numero, anio), (numero_propio, anio_propio) = index.split("/"), propio.split("/")
    if anio != anio_propio or len(numero) != len(numero_propio):
        return False
    return sum(a != b for a, b in zip(numero, numero_propio, strict=True)) == 1


def _es_descarga_de_nyscef(nombre_archivo: str, index: str) -> bool:
    coincide = NOMBRE_DE_NYSCEF.match(nombre_archivo)
    return bool(coincide) and f"{int(coincide.group(1))}/{coincide.group(2)}" == index


def _tipo_de_documento_ajeno(
    mismo_cliente: bool, propio: bool, index: str, destino: Carpeta
) -> tuple[str, str]:
    if mismo_cliente:
        return (
            "4_documento_de_otro_caso_del_cliente",
            f"El documento lleva {index}, de otro caso del mismo cliente ('{destino.titulo}'): "
            "¿va en esa carpeta?",
        )
    if propio:
        return (
            "8_index_equivocado_en_documento",
            f"El documento lleva {index}, de '{destino.titulo}': corregir antes de radicar.",
        )
    return (
        "4_documento_de_otro_cliente",
        f"El documento lleva {index}, de '{destino.titulo}': ¿mal archivado o plantilla?",
    )


def _orientar(a: Carpeta, b: Carpeta) -> tuple[Carpeta, Carpeta] | None:
    """(origen, destino): se conserva la carpeta con index; con el mismo index, la abierta."""
    if a.nombre.sin_index != b.nombre.sin_index:
        return (a, b) if a.nombre.sin_index else (b, a)
    if a.nombre.index and a.nombre.index == b.nombre.index and a.nombre.cerrado != b.nombre.cerrado:
        return (a, b) if a.nombre.cerrado else (b, a)
    return None


def citas_del_lote(indices_por_cliente: dict[str, set[str]], minimo_clientes: int) -> set[str]:
    """Index que aparecen en las carátulas de casos de muchos clientes distintos: son citas.

    Se cuenta por cliente y no por carpeta: tres carpetas del mismo cliente que citan el mismo
    pleito (Hernandez, Nelson) no hacen de ese pleito una cita.
    """
    conteo = Counter(i for indices in indices_por_cliente.values() for i in indices)
    return {i for i, n in conteo.items() if n >= minimo_clientes}
