"""Registro de JSONL revisados: qué cuenta como nuevo."""

from app.revision.vigilancia import JsonlRemoto, Registro


def test_nuevos_y_regenerados(tmp_path):
    registro = Registro(tmp_path / "revisados.json")
    a = JsonlRemoto("a", "JSONL/Casos_rafael", "Claude-1.jsonl", "2026-10-07T10:00:00Z")
    b = JsonlRemoto("b", "JSONL/Casos_gpu2", "Claude-2.jsonl", "2026-10-07T11:00:00Z")
    assert registro.nuevos([a, b]) == [a, b]
    registro.marcar([a, b])

    b_regenerado = JsonlRemoto("b", "JSONL/Casos_gpu2", "Claude-2.jsonl", "2026-10-08T09:00:00Z")
    c = JsonlRemoto("c", "JSONL/Casos_gpu3", "Claude-3.jsonl", "2026-10-08T09:00:00Z")
    assert Registro(tmp_path / "revisados.json").nuevos([a, b_regenerado, c]) == [b_regenerado, c]
