"""Vigila las carpetas de JSONL y, cuando hay suficientes nuevos, genera otro plan.

Cuenta los JSONL nuevos o regenerados en Casos_rafael, Casos_gpu2 y Casos_gpu3 desde la
última revisión. Si llegan al umbral (100 por defecto), revisa SOLO esos y deja un plan
nuevo en salida/revision/ (igual que revisar_matters). NUNCA aplica el plan: eso sigue
siendo `scripts.aplicar_plan`, después de revisarlo.

Uso:
    python -m scripts.vigilar_jsonl                  # revisa si hay 100 o más nuevos
    python -m scripts.vigilar_jsonl --umbral 50
    python -m scripts.vigilar_jsonl --marcar-hasta 2026-10-07T12:42:08
        (una vez: da por revisados los JSONL modificados antes de esa fecha, en UTC)
"""

import argparse
import sys
from datetime import UTC, datetime

from app.core.config import settings
from app.revision.trazabilidad import Trazabilidad
from app.revision.vigilancia import Registro, listar_jsonl
from app.servicios.revision import revisar_lote
from app.sharepoint import ClienteGraph
from app.validacion import leer_inventario_de_bytes


def _argumentos() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--umbral", type=int, default=100, help="JSONL nuevos para generar plan")
    parser.add_argument("--marcar-hasta", help="Fecha ISO: marcar como revisados los anteriores")
    parser.add_argument(
        "--iniciar-sesion",
        action="store_true",
        help="Abre el navegador para renovar la sesión de Microsoft (si la tarea avisa que caducó)",
    )
    return parser.parse_args()


def _a_utc(fecha: str) -> datetime:
    valor = datetime.fromisoformat(fecha.replace("Z", "+00:00"))
    return valor if valor.tzinfo else valor.astimezone().astimezone(UTC)


def main() -> int:
    args = _argumentos()
    # Sin navegador: corre desatendido. Si la sesión caducó, falla y lo dice.
    cliente = ClienteGraph(interactivo=args.iniciar_sesion)
    if args.iniciar_sesion:
        cliente.carpetas_de_casos()
        print("Sesión de Microsoft renovada.")
        return 0
    registro = Registro()
    remotos = listar_jsonl(cliente, settings.SHAREPOINT_CARPETAS_JSONL)

    if args.marcar_hasta:
        limite = _a_utc(args.marcar_hasta)
        anteriores = [r for r in remotos if r.modificado and _a_utc(r.modificado) <= limite]
        registro.marcar(anteriores)
        print(f"Marcados como revisados: {len(anteriores)} de {len(remotos)} JSONL")
        return 0

    nuevos = registro.nuevos(remotos)
    ahora = datetime.now().isoformat(timespec="seconds")
    print(
        f"{ahora}  JSONL en SharePoint: {len(remotos)}  nuevos sin revisar: {len(nuevos)}"
        f"  (umbral {args.umbral})"
    )
    traza = Trazabilidad()
    if len(nuevos) < args.umbral:
        traza.log("VIGILANCIA", f"{len(nuevos)} JSONL nuevos (umbral {args.umbral}): sin plan")
        print("Todavía no llega al umbral: no se genera plan.")
        return 0

    inventarios = [
        leer_inventario_de_bytes(cliente.descargar(r.id), f"{r.carpeta}/{r.nombre}") for r in nuevos
    ]
    resultado = revisar_lote(inventarios, cliente)
    carpetas = {c.id: c.titulo for c in resultado.matters.por_item.values()}
    traza.sincronizar(carpetas)
    traza.registrar_revision(
        resultado.plan, resultado.cobertura, {t: i for i, t in carpetas.items()}
    )
    traza.log("VIGILANCIA", f"{len(nuevos)} JSONL nuevos: plan {resultado.ruta_plan.name}")
    traza.guardar()
    registro.marcar(nuevos)
    print(
        f"Plan nuevo: {resultado.ruta_plan}  ({len(resultado.plan.acciones)} acciones, "
        f"{len(resultado.plan.hallazgos)} hallazgos)"
    )
    print("No se aplicó nada. Revísalo y, si está bien:")
    print(f'  python -m scripts.aplicar_plan "{resultado.ruta_plan}"')
    return 0


if __name__ == "__main__":
    sys.exit(main())
