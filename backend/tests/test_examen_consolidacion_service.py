"""Tests de la consolidación de exámenes → EVAL_CONOCIMIENTOS por (ciclo, país)."""
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services import examen_consolidacion_service as cons


def test_consolidar_aborta_si_ciclo_cerrado(monkeypatch):
    db = MagicMock()

    def _raise(d, c):
        raise cons.recalculo_service.CicloCerradoError("cerrado")

    monkeypatch.setattr(cons.recalculo_service, "validar_ciclo_abierto", _raise)
    out = cons.consolidar_ciclo(db, ciclo_id=7, pais_codigo="DO", usuario_id=1)
    assert out["abortado"] is True
    assert out["rms_consolidados"] == 0


def test_consolidar_escribe_y_recalcula_una_vez(monkeypatch):
    db = MagicMock()
    monkeypatch.setattr(cons.recalculo_service, "validar_ciclo_abierto", lambda d, c: None)
    rms = [SimpleNamespace(id=1, pais_codigo="DO"), SimpleNamespace(id=2, pais_codigo="DO")]
    monkeypatch.setattr(cons, "rms_del_ciclo", lambda d, c, p: rms)
    monkeypatch.setattr(cons.examen_kpi_service, "upsert_nota_rm", lambda d, rm, cid: 8.0)
    recalcs = {"n": 0}
    monkeypatch.setattr(cons.recalculo_service, "recalcular_ciclo",
                        lambda d, cid, pais: recalcs.__setitem__("n", recalcs["n"] + 1))
    monkeypatch.setattr(cons, "_upsert_estado", lambda *a, **k: None)
    out = cons.consolidar_ciclo(db, ciclo_id=7, pais_codigo="DO", usuario_id=1)
    assert out["abortado"] is False
    assert out["rms_consolidados"] == 2
    assert out["nota_promedio_equipo"] == 8.0
    assert recalcs["n"] == 1  # un único recálculo


def test_estado_consolidacion_sin_fila_es_pendiente(monkeypatch):
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    monkeypatch.setattr(cons, "rms_del_ciclo", lambda d, c, p: [])
    monkeypatch.setattr(cons.recalculo_service, "validar_ciclo_abierto", lambda d, c: None)
    out = cons.estado_consolidacion(db, ciclo_id=7, pais_codigo="DO")
    assert out["estado"] == "pendiente"
    assert out["rms_con_nota"] == 0
    assert out["ciclo_abierto"] is True
