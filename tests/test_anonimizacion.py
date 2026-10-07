"""Regla 5: lo que se enmascara y lo que tiene que sobrevivir (los index)."""

from app.limpieza.reglas import anonimizar_pii


def test_enmascara_ssn_cuentas_correos_telefonos_y_fecha_de_nacimiento():
    texto = (
        "SSN 056-88-1775. Loan No.: 195786063. Email: jdoe@gmail.com. "
        "Call (718) 555-1234 or 917.555.9876. DOB: 01/02/1980. Date of Birth March 3, 1975."
    )
    limpio = anonimizar_pii(texto)
    assert "[SSN-REDACTED-1775]" in limpio
    assert "195786063" not in limpio and "6063]" in limpio
    assert "[EMAIL-REDACTED]" in limpio and "gmail" not in limpio
    assert "[TEL-REDACTED-1234]" in limpio and "[TEL-REDACTED-9876]" in limpio
    assert limpio.count("[DOB-REDACTED]") == 2  # noqa: PLR2004
    assert "1980" not in limpio and "1975" not in limpio


def test_conserva_index_fechas_normales_y_numeros_federales():
    texto = "Index No. 826173/2025, Case 1:23-cv-01270, filed 10/06/2026 at 9:30."
    assert anonimizar_pii(texto) == texto
