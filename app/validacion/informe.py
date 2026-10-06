"""El resultado de la validación como texto legible, agrupado por carpeta."""

from collections import defaultdict

from app.validacion.comparador import BYTES_POR_MB, CARPETA_RAIZ, ResultadoValidacion

KB = 1024


def _tamano(bytes_: int) -> str:
    if bytes_ >= BYTES_POR_MB:
        return f"{bytes_ / BYTES_POR_MB:.1f} MB"
    return f"{max(bytes_ // KB, 1)} KB"


def _por_carpeta(rutas: list[str]) -> dict[str, list[str]]:
    grupos: dict[str, list[str]] = defaultdict(list)
    for ruta in sorted(rutas, key=str.casefold):
        carpeta, _, nombre = ruta.rpartition("/")
        grupos[carpeta or CARPETA_RAIZ].append(nombre)
    return dict(grupos)


def _seccion(titulo: str, grupos: dict[str, list[str]]) -> list[str]:
    total = sum(len(v) for v in grupos.values())
    lineas = ["", f"{titulo} ({total}):"]
    for carpeta, nombres in grupos.items():
        lineas.append(f"  {carpeta}/  ({len(nombres)})")
        lineas.extend(f"    - {nombre}" for nombre in nombres)
    return lineas


def _estado(resultado: ResultadoValidacion) -> str:
    if resultado.completo:
        return "COMPLETO: el JSONL tiene todos los archivos de SharePoint"
    problemas = []
    if resultado.faltantes:
        problemas.append(f"faltan {len(resultado.faltantes)} archivo(s) en el JSONL")
    if resultado.sin_id:
        problemas.append(f"{len(resultado.sin_id)} línea(s) del JSONL sin id")
    return "INCOMPLETO: " + "; ".join(problemas)


def _encabezado(resultado: ResultadoValidacion) -> list[str]:
    lineas = [
        f"Validación SharePoint vs JSONL: {resultado.caso}",
        "=" * 60,
        f"  Archivos en SharePoint: {resultado.total_sharepoint}",
        f"  Archivos en el JSONL:   {resultado.total_jsonl}",
        f"  Coinciden por id:       {len(resultado.emparejados)}",
        "",
        f"  {_estado(resultado)}",
    ]
    if resultado.caso_solicitado:
        aviso = f"  (el JSONL dice '{resultado.caso_solicitado}'; en SharePoint se llama así)"
        lineas.insert(2, aviso)
    if resultado.ignorados:
        nombres = ", ".join(a.nombre for a in resultado.ignorados)
        lineas.append(f"  (no se cuentan, no son documentos del caso: {nombres})")
    return lineas


def _por_carpetas(resultado: ResultadoValidacion) -> list[str]:
    filas = resultado.resumen_por_carpeta()
    ancho = max([len("Carpeta"), *(len(f["carpeta"]) for f in filas)])
    lineas = [
        "",
        "POR CARPETA:",
        f"  {'Carpeta':<{ancho}}  SharePoint  JSONL  Faltan",
        f"  {'-' * ancho}  ----------  -----  ------",
    ]
    for f in filas:
        marca = "  <--" if f["faltan"] else ""
        lineas.append(
            f"  {f['carpeta']:<{ancho}}  {f['en_sharepoint']:>10}  {f['en_jsonl']:>5}"
            f"  {f['faltan']:>6}{marca}"
        )
    return lineas


def _faltantes(resultado: ResultadoValidacion) -> list[str]:
    lineas = ["", f"FALTAN EN EL JSONL ({len(resultado.faltantes)}):"]
    for carpeta, archivos in resultado.faltantes_por_carpeta().items():
        lineas.append(f"  {carpeta}/  ({len(archivos)})")
        lineas.extend(
            f"    - {a.nombre}  ({_tamano(a.tamano_bytes)})  id: {a.id}" for a in archivos
        )
    return lineas


def _sobrantes(resultado: ResultadoValidacion) -> list[str]:
    return _seccion(
        "EN EL JSONL PERO YA NO EN SHAREPOINT (ese id no existe en el caso)",
        _por_carpeta([a.ruta for a in resultado.sobrantes]),
    )


def _sin_id(resultado: ResultadoValidacion) -> list[str]:
    lineas = ["", f"LÍNEAS DEL JSONL SIN ID, no se pueden validar ({len(resultado.sin_id)}):"]
    return lineas + [f"  - línea {a.linea}: {a.ruta}" for a in resultado.sin_id]


def _duplicados(resultado: ResultadoValidacion) -> list[str]:
    lineas = ["", f"ID REPETIDO EN EL JSONL ({len(resultado.duplicados)}):"]
    return lineas + [f"  - línea {a.linea}: {a.ruta}  id: {a.id}" for a in resultado.duplicados]


def _movidos(resultado: ResultadoValidacion) -> list[str]:
    lineas = ["", f"MOVIDOS O RENOMBRADOS desde la lectura ({len(resultado.movidos)}):"]
    return lineas + [f"  - {e.jsonl.ruta}  ->  {e.sharepoint.ruta}" for e in resultado.movidos]


def _tamanos(resultado: ResultadoValidacion) -> list[str]:
    return _seccion(
        "TAMAÑO DISTINTO (el archivo cambió después de leerlo)",
        _por_carpeta([e.sharepoint.ruta for e in resultado.tamano_distinto]),
    )


def _no_leidos(resultado: ResultadoValidacion) -> list[str]:
    lineas = ["", f"ESTÁN EN EL JSONL PERO SIN TEXTO ({len(resultado.no_leidos)}):"]
    return lineas + [f"  - {a.ruta}  ->  {a.motivo_no_leido}" for a in resultado.no_leidos]


SECCIONES = [
    (lambda r: r.total_sharepoint, _por_carpetas),
    (lambda r: r.faltantes, _faltantes),
    (lambda r: r.sin_id, _sin_id),
    (lambda r: r.sobrantes, _sobrantes),
    (lambda r: r.duplicados, _duplicados),
    (lambda r: r.movidos, _movidos),
    (lambda r: r.tamano_distinto, _tamanos),
    (lambda r: r.no_leidos, _no_leidos),
]


def informe_texto(resultado: ResultadoValidacion) -> str:
    lineas = _encabezado(resultado)
    for hay, seccion in SECCIONES:
        if hay(resultado):
            lineas += seccion(resultado)
    return "\n".join(lineas)


def _tabla_de_casos(resultados: list[ResultadoValidacion], errores: dict[str, str]) -> list[str]:
    nombres = [r.caso for r in resultados] + list(errores)
    ancho = max([len("Caso"), *(len(n) for n in nombres)])
    lineas = [
        f"  {'Caso':<{ancho}}  SharePoint  JSONL  Faltan  Estado",
        f"  {'-' * ancho}  ----------  -----  ------  ----------",
    ]
    for r in resultados:
        estado = "completo" if r.completo else "INCOMPLETO"
        lineas.append(
            f"  {r.caso:<{ancho}}  {r.total_sharepoint:>10}  {len(r.emparejados):>5}"
            f"  {len(r.faltantes):>6}  {estado}"
        )
    lineas += [f"  {caso:<{ancho}}  {'-':>10}  {'-':>5}  {'-':>6}  NO EXISTE" for caso in errores]
    return lineas


def informe_varios_casos(
    resultados: list[ResultadoValidacion], errores: dict[str, str], lineas_sin_caso: int
) -> str:
    """Resumen de todos los casos del JSONL y, debajo, el informe completo de cada uno."""
    completos = sum(r.completo for r in resultados)
    lineas = [
        f"Casos en el JSONL: {len(resultados) + len(errores)}   "
        f"Completos: {completos}   Incompletos: {len(resultados) - completos}   "
        f"No encontrados en SharePoint: {len(errores)}",
        "",
        "POR CASO:",
        *_tabla_de_casos(resultados, errores),
    ]
    if lineas_sin_caso:
        lineas += ["", f"  {lineas_sin_caso} línea(s) del JSONL no indican su caso: no se validan."]
    for caso, error in errores.items():
        lineas += ["", f"NO SE ENCONTRÓ '{caso}': {error}"]
    for resultado in resultados:
        lineas += ["", "", informe_texto(resultado)]
    return "\n".join(lineas)
