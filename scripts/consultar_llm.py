"""Capa 2: manda al LLM los hallazgos ambiguos de un plan, con el OCR ya limpio.

POR DEFECTO SOLO SIMULA: arma las consultas, muestra un ejemplo de lo que se enviaría (ya
con los datos personales enmascarados) y estima los tokens. No envía nada a la API.
Con --ejecutar las manda y guarda las respuestas en salida/revision/llm__<fecha>.jsonl.

Los JSONL se leen de SharePoint en memoria: no se guarda ninguna copia en disco.

Uso:
    python -m scripts.consultar_llm salida/revision/plan__<fecha>.json --max 30
    python -m scripts.consultar_llm salida/revision/plan__<fecha>.json --max 30 --ejecutar
"""

import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

from app.core.config import settings
from app.revision.llm import SISTEMA, ClasificadorLLM, armar_consulta
from app.revision.nombres import leer_nombre
from app.revision.plan import Hallazgo, Plan
from app.sharepoint import ClienteGraph

CARACTERES_POR_TOKEN = 4  # estimación para la simulación


def _argumentos() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("plan", type=Path)
    parser.add_argument("--max", type=int, default=30, help="Cuántos hallazgos enviar")
    parser.add_argument("--ejecutar", action="store_true", help="Enviar de verdad a la API")
    return parser.parse_args()


def _registros_por_caso(cliente: ClienteGraph, hallazgos: list[Hallazgo]) -> dict[str, list]:
    """{id interno: líneas de documento de su JSONL}, leídas en memoria."""
    disponibles = {
        x["name"]: x["id"]
        for carpeta in settings.SHAREPOINT_CARPETAS_JSONL
        for x in cliente.hijos_de_ruta(carpeta)
    }
    registros = {}
    for id_interno in {leer_nombre(h.carpeta).id_interno for h in hallazgos}:
        item = disponibles.get(f"Claude-{id_interno}.jsonl")
        if not item:
            continue
        lineas = cliente.descargar(item).decode("utf-8-sig", errors="replace").splitlines()
        registros[id_interno] = [
            json.loads(linea) for linea in lineas if linea.strip() and '"file_name"' in linea
        ]
    return registros


def _muestra_variada(hallazgos: list[Hallazgo], maximo: int) -> list[Hallazgo]:
    """Toma por turnos un hallazgo de cada regla, para que la muestra tenga de todo."""
    por_regla: dict[str, list[Hallazgo]] = {}
    for hallazgo in hallazgos:
        por_regla.setdefault(hallazgo.regla, []).append(hallazgo)
    muestra: list[Hallazgo] = []
    while len(muestra) < maximo and any(por_regla.values()):
        for grupo in por_regla.values():
            if grupo and len(muestra) < maximo:
                muestra.append(grupo.pop(0))
    return muestra


def _relacionadas(hallazgo: Hallazgo) -> list[str]:
    d = hallazgo.datos
    return [
        x
        for x in [
            d.get("found_index_belongs_to"),
            d.get("otra_carpeta"),
            *d.get("carpetas", []),
            *d.get("candidatas", []),
        ]
        if x
    ]


def main() -> int:
    args = _argumentos()
    plan = Plan.cargar(args.plan)
    hallazgos = _muestra_variada([h for h in plan.hallazgos if h.para_llm], args.max)
    if not hallazgos:
        print("El plan no tiene hallazgos para el LLM.")
        return 0
    registros = _registros_por_caso(ClienteGraph(), hallazgos)
    consultas = [
        armar_consulta(h, registros.get(leer_nombre(h.carpeta).id_interno, []), _relacionadas(h))
        for h in hallazgos
    ]
    caracteres = sum(len(SISTEMA) + len(c.mensaje()) for c in consultas)
    print(f"{len(consultas)} consultas, ~{caracteres // CARACTERES_POR_TOKEN:,} tokens de entrada")
    print(f"Modelo: {settings.CLAUDE_MODEL_REVISION}")
    print(f"Por regla: {dict(Counter(h.regla for h in hallazgos))}")
    print(f"Sin texto utilizable: {sum(not c.documentos for c in consultas)}")

    if not args.ejecutar:
        ejemplo = next((c for c in consultas if c.documentos), consultas[0])
        print("\n--- EJEMPLO DE LO QUE SE ENVIARÍA (ya limpio) ---")
        print(ejemplo.mensaje()[:3000])
        print("\nSIMULACIÓN: no se envió nada. Para enviarlo de verdad, añade --ejecutar.")
        return 0

    clasificador = ClasificadorLLM()
    salida = settings.REVISION_DIR / f"llm__{datetime.now().strftime('%Y%m%d-%H%M%S')}.jsonl"
    entrada = salida_tokens = 0
    with salida.open("w", encoding="utf-8") as archivo:
        for numero, consulta in enumerate(consultas, 1):
            respuesta = clasificador.decidir(consulta)
            entrada += respuesta.tokens_entrada
            salida_tokens += respuesta.tokens_salida
            archivo.write(json.dumps(respuesta.a_dict(), ensure_ascii=False) + "\n")
            estado = (
                respuesta.error
                or f"{respuesta.decision.get('decision')} ({respuesta.decision.get('confianza')})"
            )
            print(f"[{numero}/{len(consultas)}] {consulta.hallazgo.carpeta[:45]:<45} {estado}")
    print(f"\nTokens: {entrada:,} de entrada, {salida_tokens:,} de salida")
    print(f"Respuestas: {salida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
