"""Inspecciona las tablas y una muestra de registros del almacén vectorial.

Uso: python -m scripts.ver_tablas
"""

from app.persistencia import almacen_documental
from app.persistencia.modelos import Tabla
from app.persistencia.repositorio_sqlite import RepositorioSqlite
from scripts.consola import (
    ANCHO_CONSOLA,
    imprimir_seccion,
    imprimir_titulo,
    truncar,
)

MUESTRA_DOCUMENTOS = 5
MUESTRA_CHUNKS = 3

ANCHO_ID = 16
ANCHO_CASO = 22
ANCHO_ARCHIVO = 20
ANCHO_CONFIANZA = 9
ANCHO_ID_CHUNK = 5
ANCHO_INDICE_CHUNK = 8


def _imprimir_encabezado_tabla(encabezado: str) -> None:
    print(encabezado)
    print(" " + "-" * (ANCHO_CONSOLA - 2))


def _imprimir_resumen_tabla(repositorio: RepositorioSqlite, tabla: Tabla) -> None:
    print(f" Columnas: {', '.join(repositorio.columnas_de(tabla))}")
    print(f" Total registros: {repositorio.contar_registros(tabla)}\n")


def _imprimir_documentos(repositorio: RepositorioSqlite) -> None:
    imprimir_seccion(f"TABLA 1: {Tabla.DOCUMENTOS}")
    _imprimir_resumen_tabla(repositorio, Tabla.DOCUMENTOS)
    _imprimir_encabezado_tabla(
        f" {'ID':<{ANCHO_ID}} | {'Caso':<{ANCHO_CASO}} | {'Archivo':<{ANCHO_ARCHIVO}} | "
        f"{'Confianza':<{ANCHO_CONFIANZA}} | Chars"
    )
    for doc_id, caso, archivo, confianza, caracteres in repositorio.muestra_documentos(
        MUESTRA_DOCUMENTOS
    ):
        print(
            f" {truncar(doc_id, ANCHO_ID):<{ANCHO_ID}} | "
            f"{truncar(caso, ANCHO_CASO):<{ANCHO_CASO}} | "
            f"{truncar(archivo, ANCHO_ARCHIVO):<{ANCHO_ARCHIVO}} | "
            f"{f'{confianza:.1f}%':<{ANCHO_CONFIANZA}} | {caracteres}"
        )


def _imprimir_chunks(repositorio: RepositorioSqlite) -> None:
    imprimir_seccion(f"TABLA 2: {Tabla.CHUNKS} (Almacén de Embeddings)")
    _imprimir_resumen_tabla(repositorio, Tabla.CHUNKS)
    _imprimir_encabezado_tabla(
        f" {'ID':<{ANCHO_ID_CHUNK}} | {'Doc ID':<{ANCHO_ID}} | {'Chunk #':<{ANCHO_INDICE_CHUNK}} | "
        "Longitud Texto | Dimensión Vector"
    )
    for chunk_id, doc_id, indice, longitud, dimension in repositorio.muestra_chunks(MUESTRA_CHUNKS):
        print(
            f" {chunk_id:<{ANCHO_ID_CHUNK}} | {truncar(doc_id, ANCHO_ID):<{ANCHO_ID}} | "
            f"{indice:<{ANCHO_INDICE_CHUNK}} | {longitud} caracteres | {dimension} dimensiones"
        )


def _imprimir_resumen_postgres() -> None:
    print(f" Total documentos en Postgres: {almacen_documental.contar_registros(Tabla.DOCUMENTOS)}")
    print(f" Total chunks en pgvector: {almacen_documental.contar_registros(Tabla.CHUNKS)}")


def main() -> None:
    imprimir_titulo("INSPECTOR DE TABLAS Y REGISTROS - PETROFF AMSHEN LLP")
    if almacen_documental.usa_postgres:
        print("[Motor Activo]: PostgreSQL + pgvector")
        _imprimir_resumen_postgres()
        return

    repositorio = almacen_documental.sqlite
    print("[Motor Activo]: SQLite Local Fallback")
    print(f"[Archivo DB]  : {repositorio.ruta}")
    _imprimir_documentos(repositorio)
    _imprimir_chunks(repositorio)
    print("\n" + "=" * ANCHO_CONSOLA + "\n")


if __name__ == "__main__":
    main()
