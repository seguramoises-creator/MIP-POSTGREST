"""Tests Maestro de Médicos — Fase 1.3 (dedup en cascada + alta/edición central).

Convención del proyecto (ver conftest.py / test_visita_service.py): sin BD real.
`normalizar_nombre` se prueba como función pura; el branching de `crear_maestro`
se prueba monkeypatcheando `maestro_medico_service.detectar_duplicados` para
devolver dicts controlados, con un `db` MagicMock (add/commit/refresh no-ops).
"""
from unittest.mock import MagicMock

import pytest

from app.services import maestro_medico_service as svc


def test_normalizar_quita_acentos_mayusculas_y_espacios():
    assert svc.normalizar_nombre("  José   Peña ") == "JOSE PENA"


def test_normalizar_nombre_vacio():
    assert svc.normalizar_nombre("") == ""
    assert svc.normalizar_nombre(None) == ""


def _fake_db():
    db = MagicMock()
    db.refresh.side_effect = lambda obj: None
    return db


def test_crear_bloquea_por_duplicado_duro(monkeypatch):
    db = _fake_db()
    monkeypatch.setattr(
        svc, "detectar_duplicados",
        lambda *a, **k: {"duros": [{"id": 1, "nombre": "A B", "cedula": "001-1"}], "blandos": []},
    )
    with pytest.raises(svc.DuplicadoDuroError) as exc:
        svc.crear_maestro(db, "DO", {"nombre": "NUEVO", "cedula": "001-1"})
    assert exc.value.coincidencias == [{"id": 1, "nombre": "A B", "cedula": "001-1"}]
    db.add.assert_not_called()


def test_crear_advierte_por_duplicado_blando_sin_confirmar(monkeypatch):
    db = _fake_db()
    monkeypatch.setattr(
        svc, "detectar_duplicados",
        lambda *a, **k: {"duros": [], "blandos": [{"id": 5, "nombre": "JUAN PEREZ"}]},
    )
    with pytest.raises(svc.PosibleDuplicadoError) as exc:
        svc.crear_maestro(db, "DO", {"nombre": "Juan Perez", "centro_medico_id": 5})
    assert exc.value.coincidencias == [{"id": 5, "nombre": "JUAN PEREZ"}]
    db.add.assert_not_called()


def test_crear_permite_duplicado_blando_si_se_confirma(monkeypatch):
    db = _fake_db()
    monkeypatch.setattr(
        svc, "detectar_duplicados",
        lambda *a, **k: {"duros": [], "blandos": [{"id": 5, "nombre": "JUAN PEREZ"}]},
    )
    m = svc.crear_maestro(
        db, "DO", {"nombre": "Juan Perez", "centro_medico_id": 5},
        confirmar_duplicado=True,
    )
    db.add.assert_called_once()
    db.commit.assert_called_once()
    assert m.estado_validacion == "APROBADO"
    assert m.origen == "MANUAL"
    assert m.pais_codigo == "DO"
    assert m.nombre == "Juan Perez"


def test_crear_normal_sin_duplicados(monkeypatch):
    db = _fake_db()
    monkeypatch.setattr(
        svc, "detectar_duplicados",
        lambda *a, **k: {"duros": [], "blandos": []},
    )
    m = svc.crear_maestro(db, "DO", {"nombre": "NUEVO MEDICO"})
    db.add.assert_called_once()
    db.commit.assert_called_once()
    db.refresh.assert_called_once()
    assert m.estado_validacion == "APROBADO"
    assert m.origen == "MANUAL"
