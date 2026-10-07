"""Capa 2 sin llamar a la API: qué se envía (ya limpio) y cómo se lee la respuesta."""

import json
from types import SimpleNamespace

from app.revision.llm import ClasificadorLLM, armar_consulta
from app.revision.plan import Hallazgo

REGISTRO = {
    "file_name": "TRO- Luciano.docx",
    "origen": "/Matters/Jenkins, Brittney - 800066 - 0/02_FCRA Dispute",
    "read_with": "python-docx",
    "extracted_text": (
        "SUPREME COURT OF THE STATE OF NEW YORK  Index No. 505349/2023\n"
        "KATHERINE LUCIANO, Plaintiff, against BANK. SSN 056-88-1775, "
        "phone (718) 555-1234, email k.luciano@gmail.com, DOB: 01/02/1980. "
        + "The plaintiff respectfully moves this court for a temporary restraining order. "
        * 5
    ),
}
HALLAZGO = Hallazgo(
    "4_documento_de_otro_cliente",
    "El documento lleva 505349/2023, de 'Luciano, Katherine - 600847 - 505349-2023'",
    "Jenkins, Brittney - 800066 - 0",
    {
        "file_name": "TRO- Luciano.docx",
        "found_index_belongs_to": "Luciano, Katherine - 600847 - 505349-2023",
    },
    para_llm=True,
)


class ApiFalsa:
    def __init__(self, decision: dict, stop_reason: str = "end_turn") -> None:
        self.enviado = None
        self._respuesta = SimpleNamespace(
            stop_reason=stop_reason,
            model="claude-opus-5-5",
            usage=SimpleNamespace(input_tokens=900, output_tokens=120),
            content=[SimpleNamespace(type="text", text=json.dumps(decision))],
        )
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._crear))

    def _crear(self, **kwargs):
        self.enviado = kwargs
        return self._respuesta


def test_al_llm_solo_le_llega_texto_limpio_y_conserva_el_index():
    consulta = armar_consulta(HALLAZGO, [REGISTRO], ["Luciano, Katherine - 600847 - 505349-2023"])
    mensaje = consulta.mensaje()
    assert "505349/2023" in mensaje and "LUCIANO" in mensaje
    for dato in ("056-88-1775", "555-1234", "gmail.com", "01/02/1980"):
        assert dato not in mensaje
    assert "[SSN-REDACTED-1775]" in mensaje and "[DOB-REDACTED]" in mensaje


def test_lee_la_decision_y_maneja_refusal():
    decision = {
        "decision": "mover_a_otra_carpeta",
        "carpeta_destino": "Luciano, Katherine - 600847 - 505349-2023",
        "confianza": "alta",
        "motivo": "La carátula es de Luciano.",
        "evidencia": "Index No. 505349/2023",
        "regla_sugerida": "",
    }
    consulta = armar_consulta(HALLAZGO, [REGISTRO], [])
    api = ApiFalsa(decision)
    respuesta = ClasificadorLLM(cliente=api, modelo="claude-opus-5-5").decidir(consulta)
    assert respuesta.error is None and respuesta.decision["decision"] == "mover_a_otra_carpeta"
    assert api.enviado["fallbacks"] == "default"
    assert api.enviado["output_config"]["format"]["type"] == "json_schema"

    rechazo = ClasificadorLLM(cliente=ApiFalsa({}, "refusal"), modelo="x").decidir(consulta)
    assert rechazo.error and "refusal" in rechazo.error
