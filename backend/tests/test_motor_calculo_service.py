"""Tests unitarios del motor de cálculo Python (app.services.motor_calculo_service)."""
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services import motor_calculo_service as mc
from tests.conftest import FakeQuery


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


def test_rankear_desempate_por_rm():
    # dos RM con mismo score: gana el rm_id menor (posicion_global 1)
    rows = [
        {"rm_id": 5, "linea_id": 1, "gerente_id": 2, "pais_codigo": "DO", "score_total": Decimal("80.0"), "categoria_id": None},
        {"rm_id": 3, "linea_id": 1, "gerente_id": 2, "pais_codigo": "DO", "score_total": Decimal("80.0"), "categoria_id": None},
        {"rm_id": 9, "linea_id": 2, "gerente_id": 4, "pais_codigo": "DO", "score_total": Decimal("95.0"), "categoria_id": None},
    ]
    out = {r["rm_id"]: r for r in mc._rankear(rows)}
    assert out[9]["posicion_global"] == 1 and out[9]["elegible"] is True
    assert out[3]["posicion_global"] == 2   # empate: rm 3 antes que rm 5
    assert out[5]["posicion_global"] == 3
    assert out[3]["posicion_linea"] == 1 and out[5]["posicion_linea"] == 2
    assert out[9]["posicion_linea"] == 1    # otra línea
    assert out[3]["elegible"] is False


def test_categoria_de_rangos():
    cats = [
        SimpleNamespace(id=1, score_min=Decimal("90"), score_max=Decimal("100")),
        SimpleNamespace(id=2, score_min=Decimal("70"), score_max=Decimal("89.9999")),
        SimpleNamespace(id=3, score_min=None, score_max=Decimal("69.9999")),
    ]
    assert mc._categoria_de(cats, Decimal("95")) == 1
    assert mc._categoria_de(cats, Decimal("80")) == 2
    assert mc._categoria_de(cats, Decimal("50")) == 3


def test_consolidar_ranking_gerentes_ordena_por_score_desc(fake_db):
    """
    FIX (jul-2026): _consolidar_ranking_gerentes se movio aqui desde
    ranking_service.py (retirado) -- ahora corre automaticamente al final del
    Ranking Mensual real, no solo cuando alguien disparaba manualmente el
    boton de Regional/Anual.
    """
    filas = [(10, Decimal("70")), (20, Decimal("90")), (30, Decimal("80"))]
    query_scores = FakeQuery(all_result=filas)
    query_delete = MagicMock()  # db.query(RankingGerente).filter(...).delete(...)
    fake_db.query.side_effect = [query_scores, query_delete]

    mc._consolidar_ranking_gerentes(fake_db, pais_codigo="DO", ciclo_id=5)

    added = [c.args[0] for c in fake_db.add.call_args_list]
    assert [a.gerente_id for a in added] == [20, 30, 10]
    assert [a.posicion for a in added] == [1, 2, 3]
    assert all(a.pais_codigo == "DO" and a.ciclo_id == 5 for a in added)


def test_consolidar_ranking_gerentes_sin_gd_no_hace_nada(fake_db):
    fake_db.query.return_value = FakeQuery(all_result=[])
    mc._consolidar_ranking_gerentes(fake_db, pais_codigo="DO", ciclo_id=5)
    fake_db.add.assert_not_called()


def test_recalcular_aborta_ciclo_cerrado(monkeypatch):
    from app.services import recalculo_service
    db = MagicMock()

    def _raise(d, c):
        raise recalculo_service.CicloCerradoError("cerrado")
    monkeypatch.setattr(mc, "validar_ciclo_abierto", _raise)
    out = mc.recalcular_ciclo_py(db, ciclo_id=7, pais_codigo="DO")
    assert out["abortado"] is True
    assert out["filas_kpi_actualizadas"] == 0 and out["rankings_generados"] == 0
    assert "motivo" in out
