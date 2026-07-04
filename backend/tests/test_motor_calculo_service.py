"""Tests unitarios del motor de cálculo Python (app.services.motor_calculo_service)."""
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services import motor_calculo_service as mc


def test_clamp():
    assert mc._clamp(Decimal("-5"), Decimal(0), Decimal(100)) == Decimal(0)
    assert mc._clamp(Decimal("150"), Decimal(0), Decimal(100)) == Decimal(100)
    assert mc._clamp(Decimal("42.5"), Decimal(0), Decimal(100)) == Decimal("42.5")


def test_puntos_una_fila():
    # escala=1 -> valor*100; ponderacion 15 -> puntos = (cumpl/100)*15
    ri = SimpleNamespace(id=1, resultado_real=Decimal("0.80"), resultado_porcentaje=None,
                         puntos_obtenidos=None, fecha_calculo=None, indicador_id=9)
    ind = SimpleNamespace(id=9, escala=1, ponderacion_pct=Decimal("15"))
    filas = mc._calc_puntajes_filas([(ri, ind)])
    assert ri.resultado_porcentaje == Decimal("80.0")
    assert ri.puntos_obtenidos == Decimal("12.0")   # 80/100*15
    assert filas == 1


def test_puntos_escala_100_y_clamp():
    # escala=100 -> valor directo; 120 se acota a 100; ponderacion 10 -> puntos 10
    ri = SimpleNamespace(id=2, resultado_real=Decimal("120"), resultado_porcentaje=None,
                         puntos_obtenidos=None, fecha_calculo=None, indicador_id=3)
    ind = SimpleNamespace(id=3, escala=100, ponderacion_pct=Decimal("10"))
    mc._calc_puntajes_filas([(ri, ind)])
    assert ri.resultado_porcentaje == Decimal("100")
    assert ri.puntos_obtenidos == Decimal("10.0")
