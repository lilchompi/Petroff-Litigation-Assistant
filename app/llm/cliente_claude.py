"""Cliente delgado sobre la API de Anthropic para generar dictámenes."""

import anthropic

from app.core.config import settings
from app.llm.prompts import PROMPT_SISTEMA


class GeneracionDictamenError(Exception):
    """La API de Claude falló o no devolvió texto."""


class ClienteClaude:
    def __init__(self, api_key: str, modelo: str, max_tokens: int) -> None:
        self._cliente = anthropic.Anthropic(api_key=api_key)
        self._modelo = modelo
        self._max_tokens = max_tokens

    def generar_dictamen(self, mensaje_usuario: str) -> str:
        try:
            respuesta = self._cliente.messages.create(
                model=self._modelo,
                max_tokens=self._max_tokens,
                system=PROMPT_SISTEMA,
                messages=[{"role": "user", "content": mensaje_usuario}],
            )
        except anthropic.APIError as error:
            mensaje = f"Error invocando a Anthropic Claude API: {error}"
            raise GeneracionDictamenError(mensaje) from error

        texto = "\n".join(
            bloque.text for bloque in respuesta.content if bloque.type == "text"
        ).strip()
        if not texto:
            raise GeneracionDictamenError(
                f"Claude no devolvió texto (stop_reason: {respuesta.stop_reason})."
            )
        return texto


def crear_cliente_claude() -> ClienteClaude | None:
    """Devuelve el cliente si hay API key configurada; None activa el modo de demostración."""
    if not settings.ANTHROPIC_API_KEY:
        return None
    return ClienteClaude(
        api_key=settings.ANTHROPIC_API_KEY,
        modelo=settings.CLAUDE_MODEL,
        max_tokens=settings.CLAUDE_MAX_TOKENS,
    )
