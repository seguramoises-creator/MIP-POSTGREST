import pytest
from app.services import examen_ia_service as ia


def _q(**kw):
    base = {"tipo": "multi", "texto": "¿?", "opciones": ["a", "b", "c", "d"],
            "correcta": 1, "explicacion": "porque"}
    base.update(kw)
    return base


def test_validar_ok():
    out = ia.validar_preguntas_generadas([_q(), _q(tipo="caso", escenario="esc")])
    assert len(out) == 2


def test_validar_opciones_distintas_de_4_falla():
    with pytest.raises(ValueError):
        ia.validar_preguntas_generadas([_q(opciones=["a", "b", "c"])])


def test_validar_correcta_fuera_de_rango_falla():
    with pytest.raises(ValueError):
        ia.validar_preguntas_generadas([_q(correcta=5)])


def test_validar_caso_sin_escenario_falla():
    with pytest.raises(ValueError):
        ia.validar_preguntas_generadas([_q(tipo="caso")])
