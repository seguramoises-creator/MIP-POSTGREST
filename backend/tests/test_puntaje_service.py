"""
Tests unitarios — app.services.puntaje_service
Motor de conversión KPI → Puntaje (sección 9 CLAUDE.md).
"""
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.services.puntaje_service import (
    convertir_a_puntaje,
    calcular_puntaje_coaching,
    calcular_cumplimiento,
    _clamp,
)
from tests.conftest import FakeQuery


def _tabla(desde, hasta, puntos):
    return SimpleNamespace(rango_desde=Decimal(desde), rango_hasta=Decimal(hasta), puntos=Decimal(puntos))


# ---------------------------------------------------------------------------
# _clamp
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("valor,esperado", [
    (Decimal("-5"), Decimal("0")),
    (Decimal("50"), Decimal("50")),
    (Decimal("150"), Decimal("100")),
])
def test_clamp_acota_al_intervalo(valor, esperado):
    assert _clamp(valor, Decimal("0"), Decimal("100")) == esperado


# ---------------------------------------------------------------------------
# calcular_cumplimiento
# ---------------------------------------------------------------------------

def test_calcular_cumplimiento_normal():
    assert calcular_cumplimiento(Decimal("80"), Decimal("100")) == Decimal("80")


def test_calcular_cumplimiento_supera_meta_se_acota_a_100():
    assert calcular_cumplimiento(Decimal("150"), Decimal("100")) == Decimal("100")


def test_calcular_cumplimiento_meta_cero_no_divide_por_cero():
    assert calcular_cumplimiento(Decimal("50"), Decimal("0")) == Decimal("0")


def test_calcular_cumplimiento_meta_negativa():
    assert calcular_cumplimiento(Decimal("50"), Decimal("-10")) == Decimal("0")


# ---------------------------------------------------------------------------
# calcular_puntaje_coaching
# ---------------------------------------------------------------------------

def test_calcular_puntaje_coaching_pondera_cantidad_y_calidad():
    # 0.7*80 + 0.3*60 = 56 + 18 = 74
    resultado = calcular_puntaje_coaching(Decimal("80"), Decimal("60"))
    assert resultado == Decimal("74.0")


def test_calcular_puntaje_coaching_acota_a_100():
    resultado = calcular_puntaje_coaching(Decimal("200"), Decimal("200"))
    assert resultado == Decimal("100")


def test_calcular_puntaje_coaching_pesos_personalizados():
    # peso_cantidad=0.5, peso_calidad=0.5 → (0.5*100)+(0.5*0) = 50
    resultado = calcular_puntaje_coaching(
        Decimal("100"), Decimal("0"),
        peso_cantidad=Decimal("0.5"), peso_calidad=Decimal("0.5"),
    )
    assert resultado == Decimal("50.0")


# ---------------------------------------------------------------------------
# convertir_a_puntaje  (sección 9 — reglas del motor de puntaje)
# ---------------------------------------------------------------------------

def test_convertir_a_puntaje_sin_tabla_retorna_valor_directo_acotado(fake_db):
    """Sin tabla configurada → pass-through (acotado a [0,100])."""
    fake_db.query.side_effect = [FakeQuery(all_result=[])]
    resultado = convertir_a_puntaje(fake_db, indicador_id=1, valor=Decimal("65"), pais_codigo="PA")
    assert resultado == Decimal("65")


def test_convertir_a_puntaje_sin_tabla_acota_valor_directo(fake_db):
    fake_db.query.side_effect = [FakeQuery(all_result=[])]
    resultado = convertir_a_puntaje(fake_db, indicador_id=1, valor=Decimal("250"), pais_codigo="PA")
    assert resultado == Decimal("100")


def test_convertir_a_puntaje_encuentra_rango_correcto(fake_db):
    """Valor cae dentro de uno de los rangos [desde, hasta] inclusive."""
    tablas = [_tabla(0, 50, 20), _tabla(51, 80, 60), _tabla(81, 100, 100)]
    fake_db.query.side_effect = [FakeQuery(all_result=tablas)]
    resultado = convertir_a_puntaje(fake_db, indicador_id=1, valor=Decimal("70"), pais_codigo="PA")
    assert resultado == Decimal("60")


def test_convertir_a_puntaje_limites_inclusive(fake_db):
    """Los límites de rango son inclusive en ambos extremos."""
    tablas = [_tabla(0, 50, 20), _tabla(51, 80, 60)]
    fake_db.query.side_effect = [FakeQuery(all_result=tablas)]
    assert convertir_a_puntaje(fake_db, 1, Decimal("51"), pais_codigo="PA") == Decimal("60")

    fake_db.query.side_effect = [FakeQuery(all_result=tablas)]
    assert convertir_a_puntaje(fake_db, 1, Decimal("50"), pais_codigo="PA") == Decimal("20")


def test_convertir_a_puntaje_valor_supera_maximo_retorna_puntos_maximos(fake_db):
    tablas = [_tabla(0, 50, 20), _tabla(51, 80, 60)]
    fake_db.query.side_effect = [FakeQuery(all_result=tablas)]
    resultado = convertir_a_puntaje(fake_db, 1, Decimal("999"), pais_codigo="PA")
    assert resultado == Decimal("60")


def test_convertir_a_puntaje_valor_bajo_el_minimo_retorna_cero(fake_db):
    tablas = [_tabla(20, 50, 20), _tabla(51, 80, 60)]
    fake_db.query.side_effect = [FakeQuery(all_result=tablas)]
    resultado = convertir_a_puntaje(fake_db, 1, Decimal("5"), pais_codigo="PA")
    assert resultado == Decimal("0")
