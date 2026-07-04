"""Tests del puente Exámenes → EVAL_CONOCIMIENTOS (app.services.examen_kpi_service)."""
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services import examen_kpi_service as kpi


def test_nota_desde_score():
    assert kpi.nota_desde_score(85) == 8.5
    assert kpi.nota_desde_score(100) == 10.0
    assert kpi.nota_desde_score(73.4) == 7.34


def test_no_alimenta_si_evaluado_no_es_rm(monkeypatch):
    db = MagicMock()
    intento = SimpleNamespace(id=1, evaluado_tipo="GERENTE", evaluado_rm_id=None,
                              asignacion_id=1)
    # Aunque el examen estuviera marcado, un GERENTE no alimenta este indicador.
    monkeypatch.setattr(kpi, "_examen_de_intento", lambda d, i: SimpleNamespace(
        indicador_codigo="EVAL_CONOCIMIENTOS", ciclo_id=3))
    assert kpi.alimentar_eval_conocimientos(db, intento) is False


def test_no_alimenta_si_examen_no_marcado(monkeypatch):
    db = MagicMock()
    intento = SimpleNamespace(id=1, evaluado_tipo="RM", evaluado_rm_id=5,
                              asignacion_id=1)
    monkeypatch.setattr(kpi, "_examen_de_intento", lambda d, i: SimpleNamespace(
        indicador_codigo=None, ciclo_id=None))
    assert kpi.alimentar_eval_conocimientos(db, intento) is False


def test_no_alimenta_si_ciclo_cerrado(monkeypatch):
    db = MagicMock()
    intento = SimpleNamespace(id=1, evaluado_tipo="RM", evaluado_rm_id=5,
                              asignacion_id=1)
    monkeypatch.setattr(kpi, "_examen_de_intento", lambda d, i: SimpleNamespace(
        indicador_codigo="EVAL_CONOCIMIENTOS", ciclo_id=3))

    def _raise(d, c):
        raise kpi.recalculo_service.CicloCerradoError("ciclo cerrado")
    monkeypatch.setattr(kpi.recalculo_service, "validar_ciclo_abierto", _raise)
    # No debe lanzar; retorna False y no recalcula.
    assert kpi.alimentar_eval_conocimientos(db, intento) is False


def test_upsert_nota_rm_escribe_sin_recalcular(monkeypatch):
    db = MagicMock()
    rm = SimpleNamespace(id=5, pais_codigo="DO", linea_id=2, gerente_id=3)
    monkeypatch.setattr(kpi, "_nota_promedio_rm", lambda d, rid, cid: 8.5)
    monkeypatch.setattr(kpi, "_indicador_de_pais", lambda d, pais: SimpleNamespace(id=42))
    nota = kpi.upsert_nota_rm(db, rm, ciclo_id=7)
    assert nota == 8.5
    # Escribe a la FACT pero NO recalcula (eso lo hace la consolidación 1 sola vez).
    assert db.add.called


def test_upsert_nota_rm_sin_indicador_devuelve_none(monkeypatch):
    db = MagicMock()
    rm = SimpleNamespace(id=5, pais_codigo="DO", linea_id=2, gerente_id=3)
    monkeypatch.setattr(kpi, "_indicador_de_pais", lambda d, pais: None)
    assert kpi.upsert_nota_rm(db, rm, ciclo_id=7) is None
