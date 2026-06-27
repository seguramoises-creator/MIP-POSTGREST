"""
Tests unitarios — app.services.iup_service
Motor de Score Integral / IUP (sección 7 CLAUDE.md).

Cubre especialmente la regla FIX W-08 / pendiente "IUP consistencia
completo": el componente de consistencia se calcula como el promedio del
score consolidado (FACT_ScoreIntegralRM.score_total) de los últimos 3
ciclos previos del RM, usando los disponibles si tiene menos de 3, y 0
como base neutral si no tiene historial.
"""
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.services import iup_service
from app.services.iup_service import (
    _get_puntaje_consistencia,
    _obtener_pesos,
    calcular_iup,
    _PESOS_DEFECTO,
)
from tests.conftest import FakeQuery


def _score_row(valor):
    """
    Simula una fila Row `(score_total,)` retornada por
    `db.query(ScoreIntegralRM.score_total)...all()`.
    SQLAlchemy entrega objetos Row indexables por posición (r[0]),
    no atributos sueltos — de ahí la tupla en lugar de SimpleNamespace.
    """
    return (Decimal(str(valor)) if valor is not None else None,)


# ---------------------------------------------------------------------------
# _get_puntaje_consistencia — FIX W-08 / pendiente "consistencia real"
# ---------------------------------------------------------------------------

def test_consistencia_sin_historial_retorna_base_neutral_cero(fake_db):
    """RM nuevo sin ciclos previos → 0 (no 50): evita ventaja artificial."""
    fake_db.query.return_value = FakeQuery(all_result=[])
    resultado = _get_puntaje_consistencia(fake_db, rm_id=1, pais_codigo="PA", ciclo_id=5)
    assert resultado == Decimal("0")


def test_consistencia_un_solo_ciclo_previo_usa_ese_valor(fake_db):
    """Con menos de 3 ciclos → promedio de los disponibles."""
    fake_db.query.return_value = FakeQuery(all_result=[_score_row("80")])
    resultado = _get_puntaje_consistencia(fake_db, rm_id=1, pais_codigo="PA", ciclo_id=5)
    assert resultado == Decimal("80")


def test_consistencia_dos_ciclos_previos_promedia_los_disponibles(fake_db):
    fake_db.query.return_value = FakeQuery(all_result=[_score_row("80"), _score_row("60")])
    resultado = _get_puntaje_consistencia(fake_db, rm_id=1, pais_codigo="PA", ciclo_id=5)
    assert resultado == Decimal("70")


def test_consistencia_tres_o_mas_ciclos_promedia_los_3_mas_recientes(fake_db):
    """
    El query ya ordena por (anio,numero) desc y aplica .limit(3): aquí se
    valida que la función promedia exactamente lo que el query retorna,
    sin recortar ni reordenar de más (la responsabilidad de "los 3 más
    recientes" es del ORDER BY + LIMIT en la consulta).
    """
    filas = [_score_row("90"), _score_row("80"), _score_row("70")]
    fake_db.query.return_value = FakeQuery(all_result=filas)
    resultado = _get_puntaje_consistencia(fake_db, rm_id=1, pais_codigo="PA", ciclo_id=5)
    assert resultado == Decimal("80")  # (90+80+70)/3


def test_consistencia_maneja_score_nulo_como_cero(fake_db):
    """Si alguna fila histórica tiene score_total NULL, se trata como 0."""
    fake_db.query.return_value = FakeQuery(all_result=[_score_row("100"), _score_row(None)])
    resultado = _get_puntaje_consistencia(fake_db, rm_id=1, pais_codigo="PA", ciclo_id=5)
    assert resultado == Decimal("50")  # (100+0)/2


# ---------------------------------------------------------------------------
# _obtener_pesos — FIX C-02 (pesos dinámicos desde DIM_Indicador.peso_iup)
# ---------------------------------------------------------------------------

def test_obtener_pesos_usa_defecto_si_no_hay_configuracion(fake_db):
    fake_db.query.return_value = FakeQuery(all_result=[])
    pesos = _obtener_pesos(fake_db)
    assert pesos == _PESOS_DEFECTO


def test_obtener_pesos_normaliza_para_sumar_uno(fake_db):
    """Pesos configurados que no suman 1.0 deben normalizarse."""
    filas = [
        SimpleNamespace(modulo="GESTION", peso_total=Decimal("0.6")),
        SimpleNamespace(modulo="RESULTADOS", peso_total=Decimal("0.6")),
    ]
    fake_db.query.return_value = FakeQuery(all_result=filas)
    pesos = _obtener_pesos(fake_db)

    # Garantiza la clave CONSISTENCIA aunque no venga de DIM_Indicador
    assert "CONSISTENCIA" in pesos
    # La suma total de todos los pesos debe ser 1.0 (dentro de tolerancia decimal)
    assert abs(sum(pesos.values()) - Decimal("1")) < Decimal("0.0001")


def test_obtener_pesos_garantiza_clave_consistencia_si_falta(fake_db):
    filas = [SimpleNamespace(modulo="GESTION", peso_total=Decimal("1.0"))]
    fake_db.query.return_value = FakeQuery(all_result=filas)
    pesos = _obtener_pesos(fake_db)
    assert pesos["CONSISTENCIA"] == _PESOS_DEFECTO["CONSISTENCIA"]


# ---------------------------------------------------------------------------
# calcular_iup — agregación ponderada y acotamiento a [0, 100]
# ---------------------------------------------------------------------------

def test_calcular_iup_agrega_componentes_ponderados_y_acota(fake_db):
    """
    Reemplaza los componentes por valores fijos y verifica que:
      - se agreguen ponderando según los pesos
      - el resultado quede acotado a [0, 100]
      - todas las claves iup_* / score_total estén presentes
    """
    pesos_fijos = {
        "PRODUCTIVIDAD": Decimal("0.30"),
        "COMERCIAL": Decimal("0.30"),
        "COACHING": Decimal("0.15"),
        "CAPACITACION": Decimal("0.10"),
        "CONSISTENCIA": Decimal("0.15"),
    }
    with patch.object(iup_service, "_obtener_pesos", return_value=pesos_fijos), \
         patch.object(iup_service, "_get_puntaje_productividad", return_value=Decimal("100")), \
         patch.object(iup_service, "_get_puntaje_comercial", return_value=Decimal("100")), \
         patch.object(iup_service, "_get_puntaje_coaching", return_value=Decimal("100")), \
         patch.object(iup_service, "_get_puntaje_capacitacion", return_value=Decimal("100")), \
         patch.object(iup_service, "_get_puntaje_consistencia", return_value=Decimal("100")):
        resultado = calcular_iup(fake_db, rm_id=1, pais_codigo="PA", ciclo_id=5)

    # Todos los componentes en 100 con pesos que suman 1.0 → score = 100
    assert resultado["score_total"] == Decimal("100.0000")
    assert resultado["iup_total"] == resultado["score_total"]
    assert resultado["rm_id"] == 1
    assert resultado["ciclo_id"] == 5
    for clave in ("iup_productividad", "iup_comercial", "iup_coaching",
                  "iup_capacitacion", "iup_consistencia"):
        assert resultado[clave] == Decimal("100")


def test_calcular_iup_nunca_excede_100_ni_baja_de_0(fake_db):
    pesos_fijos = {"PRODUCTIVIDAD": Decimal("1.0"), "COMERCIAL": Decimal("0"),
                   "COACHING": Decimal("0"), "CAPACITACION": Decimal("0"),
                   "CONSISTENCIA": Decimal("0")}
    with patch.object(iup_service, "_obtener_pesos", return_value=pesos_fijos), \
         patch.object(iup_service, "_get_puntaje_productividad", return_value=Decimal("9999")), \
         patch.object(iup_service, "_get_puntaje_comercial", return_value=Decimal("0")), \
         patch.object(iup_service, "_get_puntaje_coaching", return_value=Decimal("0")), \
         patch.object(iup_service, "_get_puntaje_capacitacion", return_value=Decimal("0")), \
         patch.object(iup_service, "_get_puntaje_consistencia", return_value=Decimal("0")):
        resultado = calcular_iup(fake_db, rm_id=1, pais_codigo="PA", ciclo_id=5)

    assert resultado["score_total"] == Decimal("100")
    assert resultado["score_total"] <= Decimal("100")
    assert resultado["score_total"] >= Decimal("0")
