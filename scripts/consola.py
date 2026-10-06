"""Utilidades de formato para la salida en consola de los scripts."""

ANCHO_CONSOLA = 75
ELIPSIS = "..."


def imprimir_titulo(titulo: str) -> None:
    print("\n" + "=" * ANCHO_CONSOLA)
    print(f"  {titulo}")
    print("=" * ANCHO_CONSOLA)


def imprimir_seccion(titulo: str) -> None:
    print("\n" + "-" * ANCHO_CONSOLA)
    print(f"  {titulo}")
    print("-" * ANCHO_CONSOLA)


def imprimir_separador() -> None:
    print("-" * ANCHO_CONSOLA)


def truncar(texto: str, ancho: int) -> str:
    if len(texto) <= ancho:
        return texto
    return texto[: ancho - len(ELIPSIS)] + ELIPSIS
