from types import SimpleNamespace
from app.api.v1.routers.admin import _ciclo_actual_de


def _c(anio, numero, cerrado):
    return SimpleNamespace(anio=anio, numero=numero, cerrado=cerrado)


def test_toma_el_abierto_mas_reciente():
    ciclos = [_c(2026, 1, False), _c(2026, 3, False), _c(2026, 2, True)]
    assert _ciclo_actual_de(ciclos).numero == 3


def test_ignora_los_cerrados():
    ciclos = [_c(2026, 5, True), _c(2026, 2, False)]
    assert _ciclo_actual_de(ciclos).numero == 2


def test_none_si_ninguno_abierto():
    assert _ciclo_actual_de([_c(2026, 1, True)]) is None


def test_none_si_lista_vacia():
    assert _ciclo_actual_de([]) is None
