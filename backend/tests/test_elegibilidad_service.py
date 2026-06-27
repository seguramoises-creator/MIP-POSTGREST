"""
Tests unitarios — app.services.elegibilidad_service
Motor de Elegibilidad: ELEGIBLE | NO_ELEGIBLE | CONDICIONADO.
"""
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.services import elegibilidad_service
from app.services.elegibilidad_service import (
    evaluar_elegibilidad_rm,
    _es_condicionado,
    _tiene_condicionado,
)
from tests.conftest import FakeQuery


def _regla(nombre, codigo, umbral, aplica_ranking=True, aplica_reconocimiento=True, ciclo_id=None):
    return SimpleNamespace(
        nombre=nombre, indicador_codigo=codigo, umbral_minimo=Decimal(str(umbral)),
        aplica_ranking=aplica_ranking, aplica_reconocimiento=aplica_reconocimiento,
        ciclo_id=ciclo_id,
    )


def _rm(id_=1, nombre="Juan Pérez"):
    return SimpleNamespace(id=id_, nombre=nombre)


# ---------------------------------------------------------------------------
# _es_condicionado / _tiene_condicionado — helpers puros
# ---------------------------------------------------------------------------

def test_es_condicionado_solo_si_aplica_reconocimiento_y_no_ranking():
    regla_condicionada = _regla("R1", "COACHING", 80, aplica_ranking=False, aplica_reconocimiento=True)
    regla_normal = _regla("R2", "COACHING", 80, aplica_ranking=True, aplica_reconocimiento=True)
    regla_solo_ranking = _regla("R3", "COACHING", 80, aplica_ranking=True, aplica_reconocimiento=False)

    assert _es_condicionado(regla_condicionada) is True
    assert _es_condicionado(regla_normal) is False
    assert _es_condicionado(regla_solo_ranking) is False


def test_tiene_condicionado_detecta_al_menos_una():
    reglas = [
        _regla("R1", "COACHING", 80, aplica_ranking=True, aplica_reconocimiento=True),
        _regla("R2", "CAPACITACION", 70, aplica_ranking=False, aplica_reconocimiento=True),
    ]
    assert _tiene_condicionado(reglas) is True
    assert _tiene_condicionado(reglas[:1]) is False


# ---------------------------------------------------------------------------
# evaluar_elegibilidad_rm — flujo completo
# ---------------------------------------------------------------------------

def test_rm_no_encontrado_retorna_no_elegible(fake_db):
    fake_db.query.return_value = FakeQuery(first_result=None)
    resultado = evaluar_elegibilidad_rm(fake_db, rm_id=999, pais_codigo="PA")
    assert resultado["elegible"] is False
    assert resultado["estado"] == "NO_ELEGIBLE"
    assert "no encontrado" in resultado["detalle"].lower()


def test_sin_reglas_configuradas_es_elegible_por_defecto(fake_db):
    fake_db.query.side_effect = [
        FakeQuery(first_result=_rm()),     # query RM
        FakeQuery(all_result=[]),          # query reglas (vacío)
    ]
    resultado = evaluar_elegibilidad_rm(fake_db, rm_id=1, pais_codigo="PA")
    assert resultado["elegible"] is True
    assert resultado["estado"] == "ELEGIBLE"
    assert resultado["reglas_evaluadas"] == []


def test_cumple_todas_las_reglas_es_elegible(fake_db):
    reglas = [_regla("Cobertura mínima", "COACHING", 70)]
    fake_db.query.side_effect = [
        FakeQuery(first_result=_rm()),
        FakeQuery(all_result=reglas),
    ]
    with patch.object(elegibilidad_service, "_obtener_valor_indicador", return_value=Decimal("85")):
        resultado = evaluar_elegibilidad_rm(fake_db, rm_id=1, pais_codigo="PA", ciclo_id=5)

    assert resultado["elegible"] is True
    assert resultado["estado"] == "ELEGIBLE"
    assert resultado["incumplimientos"] == 0
    assert resultado["reglas_cumplidas"] == 1
    assert resultado["reglas_evaluadas"][0]["cumple"] is True


def test_incumple_regla_normal_es_no_elegible(fake_db):
    """Una regla incumplida que NO es condicionada bloquea ranking y reconocimiento."""
    reglas = [_regla("Cobertura mínima", "COACHING", 70, aplica_ranking=True, aplica_reconocimiento=True)]
    fake_db.query.side_effect = [
        FakeQuery(first_result=_rm()),
        FakeQuery(all_result=reglas),
    ]
    with patch.object(elegibilidad_service, "_obtener_valor_indicador", return_value=Decimal("50")):
        resultado = evaluar_elegibilidad_rm(fake_db, rm_id=1, pais_codigo="PA", ciclo_id=5)

    assert resultado["elegible"] is False
    assert resultado["estado"] == "NO_ELEGIBLE"
    assert resultado["incumplimientos"] == 1


def test_incumple_unica_regla_condicionada_resulta_condicionado(fake_db):
    """
    Si la ÚNICA regla incumplida es "condicionada" (aplica solo a
    reconocimiento, no a ranking), el estado es CONDICIONADO en lugar
    de NO_ELEGIBLE — no bloquea por completo al RM.
    """
    reglas = [_regla("Capacitación obligatoria", "CAPACITACION", 90,
                     aplica_ranking=False, aplica_reconocimiento=True)]
    fake_db.query.side_effect = [
        FakeQuery(first_result=_rm()),
        FakeQuery(all_result=reglas),
    ]
    with patch.object(elegibilidad_service, "_obtener_valor_indicador", return_value=Decimal("60")):
        resultado = evaluar_elegibilidad_rm(fake_db, rm_id=1, pais_codigo="PA", ciclo_id=5)

    assert resultado["estado"] == "CONDICIONADO"
    assert resultado["elegible"] is False
    assert resultado["incumplimientos"] == 1


def test_umbral_se_evalua_como_mayor_o_igual(fake_db):
    """El cumplimiento es valor_actual >= umbral_minimo (límite inclusive)."""
    reglas = [_regla("Umbral exacto", "COACHING", 80)]
    fake_db.query.side_effect = [
        FakeQuery(first_result=_rm()),
        FakeQuery(all_result=reglas),
    ]
    with patch.object(elegibilidad_service, "_obtener_valor_indicador", return_value=Decimal("80")):
        resultado = evaluar_elegibilidad_rm(fake_db, rm_id=1, pais_codigo="PA", ciclo_id=5)

    assert resultado["reglas_evaluadas"][0]["cumple"] is True
    assert resultado["estado"] == "ELEGIBLE"


# ---------------------------------------------------------------------------
# _obtener_valor_indicador — ramas por tipo de indicador
# ---------------------------------------------------------------------------

def test_obtener_valor_indicador_capacitacion_calcula_tasa_aprobacion(fake_db):
    """aprobados/total * 100, evitando división por cero (usa 1 como piso)."""
    fake_db.query.side_effect = [
        FakeQuery(scalar_result=10),  # total
        FakeQuery(scalar_result=8),   # aprobados
    ]
    valor = elegibilidad_service._obtener_valor_indicador(
        fake_db, rm_id=1, pais_codigo="PA", ciclo_id=5, indicador_codigo="CAPACITACION"
    )
    assert valor == Decimal("80")


def test_obtener_valor_indicador_codigo_desconocido_retorna_cero(fake_db):
    valor = elegibilidad_service._obtener_valor_indicador(
        fake_db, rm_id=1, pais_codigo="PA", ciclo_id=5, indicador_codigo="CODIGO_INEXISTENTE"
    )
    assert valor == Decimal("0")
