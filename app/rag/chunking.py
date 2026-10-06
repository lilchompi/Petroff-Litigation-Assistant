"""Divide documentos en fragmentos (chunks) respetando los límites de párrafo."""

from app.core.config import settings
from app.limpieza.patrones import SEPARADOR_DE_PARRAFO


def dividir_en_chunks(texto: str, maximo_palabras: int = settings.CHUNK_SIZE_PALABRAS) -> list[str]:
    """Agrupa párrafos completos hasta alcanzar `maximo_palabras` por chunk."""
    chunks: list[str] = []
    parrafos_del_chunk: list[str] = []
    palabras_del_chunk = 0

    for parrafo in texto.split(SEPARADOR_DE_PARRAFO):
        palabras_del_parrafo = len(parrafo.split())
        excede_limite = palabras_del_chunk + palabras_del_parrafo > maximo_palabras
        if excede_limite and parrafos_del_chunk:
            chunks.append(SEPARADOR_DE_PARRAFO.join(parrafos_del_chunk))
            parrafos_del_chunk = []
            palabras_del_chunk = 0
        parrafos_del_chunk.append(parrafo)
        palabras_del_chunk += palabras_del_parrafo

    chunks.append(SEPARADOR_DE_PARRAFO.join(parrafos_del_chunk))
    return chunks
