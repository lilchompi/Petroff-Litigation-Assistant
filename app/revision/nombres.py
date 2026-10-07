"""El nombre de una carpeta de matter: 'Apellido, Nombre - <ID interno> - <index>'.

El index es lo único que identifica un caso. El nombre del cliente solo se usa como freno
para no fusionar carpetas de dos personas distintas.
"""

import re
import unicodedata
from dataclasses import dataclass, field

SEPARADOR = " - "
ESTADOS = {"closed", "open", "active"}
SIN_INDEX = "0"
# El primer dígito del ID interno es el tipo de caso (guía de revisión de calidad).
TIPOS_DE_CASO = {
    "1": "Time-Barred Debt",
    "2": "Article 15",
    "4": "ID Theft + WF Reporting",
    "5": "Chapter 7/13",
    "6": "Foreclosure y Appeal",
    "7": "RESPA Violation",
    "8": "Identity Theft",
    "9": "Wrongful Reporting",
}
ID_INTERNO = re.compile(r"^\d{6}$")
INDEX_ESTATAL = re.compile(r"^(\d{3,7})\s*[-/_]\s*((?:19|20)\d{2})$")
INDEX_FEDERAL = re.compile(r"^(\d)[-:_](\d{2})-cv-(\d{3,5})$", re.IGNORECASE)
DIGITOS_FEDERAL = 5
PALABRA = re.compile(r"[a-z0-9]+")
# Para saber si un nombre de archivo menciona al cliente ('LLC' o 'Jr' no cuentan).
LARGO_MINIMO_PALABRA = 3
PALABRAS_COMUNES = {
    "llc", "inc", "corp", "the", "and", "trust", "group", "management", "realty", "street",
    "east", "west", "north", "south", "estate", "of",
}  # fmt: skip


def index_federal(distrito: str, anio: str, numero: str) -> str:
    """'1', '23', '1270' -> '1:23-cv-01270'. El número se rellena a 5 dígitos."""
    return f"{distrito}:{anio}-cv-{int(numero):0{DIGITOS_FEDERAL}d}"


def normalizar_index(texto: str | None) -> str | None:
    """'826173-2025' -> '826173/2025'; '1-26-cv-3144' -> '1:26-cv-03144'. None si no lo es."""
    if not texto:
        return None
    valor = texto.strip()
    if estatal := INDEX_ESTATAL.match(valor):
        return f"{int(estatal.group(1))}/{estatal.group(2)}"
    if federal := INDEX_FEDERAL.match(valor):
        return index_federal(*federal.groups())
    return None


def index_para_nombre(index: str) -> str:
    """El index como va en un nombre de carpeta: '826173/2025' -> '826173-2025'."""
    return index.replace("/", "-").replace(":", "-")


def _palabras(texto: str) -> set[str]:
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return set(PALABRA.findall(sin_tildes.casefold()))


@dataclass(frozen=True)
class NombreCarpeta:
    original: str
    cliente: str
    cerrado: bool
    id_interno: str | None
    index: str | None  # normalizado; None si falta o termina en '- 0'
    index_tal_cual: str | None
    problemas: list[str] = field(default_factory=list)

    @property
    def palabras_cliente(self) -> set[str]:
        return _palabras(self.cliente)

    @property
    def sin_index(self) -> bool:
        return self.index_tal_cual in (None, SIN_INDEX)


def _problemas(id_interno: str | None, index_crudo: str | None, index: str | None) -> list[str]:
    problemas = []
    if not id_interno:
        problemas.append("no tiene ID interno de 6 dígitos")
    elif id_interno[0] not in TIPOS_DE_CASO:
        problemas.append(f"el ID interno empieza en {id_interno[0]}, que no es un tipo de caso")
    if index_crudo not in (None, SIN_INDEX) and index is None:
        problemas.append(f"el index '{index_crudo}' no tiene forma de index")
    return problemas


def leer_nombre(nombre: str) -> NombreCarpeta:
    partes = [p.strip() for p in nombre.replace("\xa0", " ").split(SEPARADOR) if p.strip()]
    utiles = [p for p in partes if p.casefold() not in ESTADOS]
    posicion = next((i for i, p in enumerate(utiles) if ID_INTERNO.match(p)), None)
    id_interno = utiles[posicion] if posicion is not None else None
    cliente = SEPARADOR.join(utiles[:posicion]) if posicion else (utiles[0] if utiles else "")
    despues = utiles[posicion + 1 :] if posicion is not None else []
    index_crudo = despues[-1] if despues else None
    index = normalizar_index(index_crudo)
    return NombreCarpeta(
        original=nombre,
        cliente=cliente,
        cerrado=any(p.casefold() == "closed" for p in partes),
        id_interno=id_interno,
        index=index,
        index_tal_cual=index_crudo,
        problemas=_problemas(id_interno, index_crudo, index),
    )


def mismo_nombre(a: NombreCarpeta, b: NombreCarpeta) -> bool:
    """Todas las palabras del nombre más corto están en el más largo, en cualquier orden.

    'Kooperling, Matias' = 'Matias, Kooperling'; 'Choi, Younga' = 'Choi, Younga T.'.
    """
    pa, pb = a.palabras_cliente, b.palabras_cliente
    if not pa or not pb:
        return False
    corto, largo = (pa, pb) if len(pa) <= len(pb) else (pb, pa)
    return corto <= largo


def nombre_menciona_cliente(nombre_archivo: str, carpeta: NombreCarpeta) -> bool:
    """El nombre del archivo lleva alguna palabra significativa del cliente de la carpeta."""
    largas = {
        p
        for p in carpeta.palabras_cliente
        if len(p) >= LARGO_MINIMO_PALABRA and not p.isdigit() and p not in PALABRAS_COMUNES
    }
    return bool(largas & _palabras(nombre_archivo))
