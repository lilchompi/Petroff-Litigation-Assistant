"""Generación de embeddings normalizados (L2) para la búsqueda vectorial.

Usa sentence-transformers cuando está disponible; si no, recurre a un vector
determinista basado en hashing de palabras para entornos ligeros.
"""

import logging
import math
import zlib
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)


def _vector_por_hashing(texto: str, dimension: int) -> list[float]:
    """Vector determinista: cada palabra suma a una posición, con peso decreciente por orden."""
    vector = [0.0] * dimension
    for posicion, palabra in enumerate(texto.lower().split()):
        indice = zlib.crc32(palabra.encode("utf-8")) % dimension
        vector[indice] += 1.0 / (1.0 + math.log1p(posicion))

    norma = math.sqrt(sum(componente * componente for componente in vector))
    if not norma:
        return vector
    return [componente / norma for componente in vector]


class GeneradorEmbeddings:
    def __init__(self, nombre_modelo: str, dimension: int, tamano_lote: int) -> None:
        self._nombre_modelo = nombre_modelo
        self._dimension = dimension
        self._tamano_lote = tamano_lote
        self._modelo: Any = None
        self._modelo_cargado = False

    def _obtener_modelo(self) -> Any:
        """Carga el modelo en el primer uso: importarlo es costoso y no siempre está instalado."""
        if not self._modelo_cargado:
            self._modelo_cargado = True
            try:
                from sentence_transformers import SentenceTransformer  # noqa: PLC0415

                self._modelo = SentenceTransformer(self._nombre_modelo)
            except ImportError:
                logger.warning("sentence-transformers no disponible; se usarán embeddings hash.")
        return self._modelo

    def generar(self, texto: str) -> list[float]:
        return self.generar_lote([texto])[0]

    def generar_lote(self, textos: list[str]) -> list[list[float]]:
        modelo = self._obtener_modelo()
        if modelo is None:
            return [_vector_por_hashing(texto, self._dimension) for texto in textos]
        vectores = modelo.encode(textos, normalize_embeddings=True, batch_size=self._tamano_lote)
        return vectores.tolist()


generador_embeddings = GeneradorEmbeddings(
    nombre_modelo=settings.EMBEDDING_MODEL_NAME,
    dimension=settings.EMBEDDING_DIM,
    tamano_lote=settings.EMBEDDING_BATCH_SIZE,
)
