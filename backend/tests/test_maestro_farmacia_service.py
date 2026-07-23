"""Tests Maestro de Farmacias — Tarea 2 (nombre_completo + anti-dup + alta).

Convención del proyecto (ver test_maestro_medico_service.py): sin BD real para las
funciones puras; `detectar_duplicados`/`crear_maestro` se prueban con dobles de
Session (MagicMock / doble de query) o monkeypatch, igual que el módulo de Médicos.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services import maestro_farmacia_service as svc


# ── Funciones puras ─────────────────────────────────────────────────────────────
def test_nombre_completo_de_cadena():
    assert svc.nombre_completo({"es_cadena": True, "cadena": "GBC", "sucursal": "Pantoja"}) == "GBC PANTOJA"


def test_nombre_completo_no_cadena_usa_nombre():
    assert svc.nombre_completo({"es_cadena": False, "nombre": "Farmacia Sol"}) == "FARMACIA SOL"


def test_nombre_completo_de_cadena_normaliza_acentos_y_espacios():
    assert svc.nombre_completo(
        {"es_cadena": True, "cadena": "  gbc ", "sucursal": " Villa   Mella "}
    ) == "GBC VILLA MELLA"


def test_normalizar():
    assert svc.normalizar("  José   Peña ") == "JOSE PENA"
    assert svc.normalizar("") == ""
    assert svc.normalizar(None) == ""


# ── detectar_duplicados: DURO por (pais, cadena, sucursal) normalizados ─────────
class _Q:
    """Doble de Session.query(...).filter(...).all() controlado por fila."""
    def __init__(self, rows): self._rows = rows
    def filter(self, *a, **k): return self
    def all(self): return self._rows


def _cand(**kw):
    base = dict(id=1, cadena="X", sucursal="Y", nombre=None, nombre_completo="X Y",
                estado="ACTIVA", direccion=None, encargado=None)
    base.update(kw)
    return SimpleNamespace(**base)


def test_detectar_duro_por_cadena_sucursal_normalizados():
    db = MagicMock()
    db.query.side_effect = [_Q([_cand(id=3, cadena="gbc", sucursal="  Pantoja ")])]
    res = svc.detectar_duplicados(db, "DO", cadena="GBC", sucursal="pantoja")
    assert [d["id"] for d in res["duros"]] == [3]


def test_detectar_duplicados_sin_coincidencia():
    db = MagicMock()
    db.query.side_effect = [_Q([_cand(id=3, cadena="OTRA", sucursal="OTRA SUCURSAL")])]
    res = svc.detectar_duplicados(db, "DO", cadena="GBC", sucursal="Pantoja")
    assert res["duros"] == []


# ── detectar_posibles_duplicados: BLANDA (informativa) por prefijo — bandeja del GD (§3.2) ──
def test_detectar_posibles_duplicados_por_prefijo():
    db = MagicMock()
    db.query.side_effect = [_Q([_cand(id=9, nombre_completo="GBC PANTOJA", estado="ACTIVA")])]
    res = svc.detectar_posibles_duplicados(db, "DO", nombre_completo="GBC PANTOJA 2")
    assert [d["id"] for d in res] == [9]


def test_detectar_posibles_duplicados_prefijo_en_sentido_inverso():
    db = MagicMock()
    db.query.side_effect = [_Q([_cand(id=9, nombre_completo="GBC PANTOJA 2", estado="ACTIVA")])]
    res = svc.detectar_posibles_duplicados(db, "DO", nombre_completo="GBC PANTOJA")
    assert [d["id"] for d in res] == [9]


def test_detectar_posibles_duplicados_sin_coincidencia():
    db = MagicMock()
    db.query.side_effect = [_Q([_cand(id=9, nombre_completo="FARMACIA CARIBE", estado="ACTIVA")])]
    res = svc.detectar_posibles_duplicados(db, "DO", nombre_completo="GBC PANTOJA")
    assert res == []


def test_detectar_posibles_duplicados_nombre_vacio_no_consulta_bd():
    db = MagicMock()
    res = svc.detectar_posibles_duplicados(db, "DO", nombre_completo="")
    assert res == []
    db.query.assert_not_called()


# ── crear_maestro / validar_bloqueantes / anti-dup integrados ───────────────────
def _fake_db():
    db = MagicMock()
    db.refresh.side_effect = lambda obj: None
    return db


def test_crear_maestro_bloquea_por_duplicado_duro(monkeypatch):
    db = _fake_db()
    monkeypatch.setattr(
        svc, "detectar_duplicados",
        lambda *a, **k: {"duros": [{"id": 1, "cadena": "GBC", "sucursal": "Pantoja"}]},
    )
    datos = {"direccion": "Calle 1", "encargado": "Ana", "cadena": "GBC", "sucursal": "Pantoja",
             "es_cadena": True}
    with pytest.raises(svc.DuplicadoDuroError) as exc:
        svc.crear_maestro(db, "DO", datos)
    assert exc.value.coincidencias == [{"id": 1, "cadena": "GBC", "sucursal": "Pantoja"}]
    db.add.assert_not_called()


def test_crear_maestro_bloquea_por_bloqueante_antes_de_anti_dup(monkeypatch):
    db = _fake_db()
    llamado = {"detectar": False}
    monkeypatch.setattr(
        svc, "detectar_duplicados",
        lambda *a, **k: (llamado.__setitem__("detectar", True) or {"duros": []}),
    )
    with pytest.raises(ValueError, match="dirección"):
        svc.crear_maestro(db, "DO", {"direccion": "  ", "encargado": "Ana"})
    assert llamado["detectar"] is False
    db.add.assert_not_called()


def test_crear_maestro_ok_setea_nombre_completo_y_audita(monkeypatch):
    db = _fake_db()
    monkeypatch.setattr(svc, "detectar_duplicados", lambda *a, **k: {"duros": []})
    datos = {"direccion": "Calle 1", "encargado": "Ana", "cadena": "GBC", "sucursal": "Pantoja",
             "es_cadena": True}
    f = svc.crear_maestro(db, "DO", datos, usuario_id=7)
    assert f.nombre_completo == "GBC PANTOJA"
    assert f.pais_codigo == "DO"
    assert f.estado == "PENDIENTE_APROBACION"
    assert f.origen == "VM"
    assert db.add.call_count == 2  # farmacia + registro de auditoría
    db.commit.assert_called_once()


def test_actualizar_maestro_recalcula_nombre_completo(monkeypatch):
    db = _fake_db()
    f = SimpleNamespace(id=1, es_cadena=True, cadena="GBC", sucursal="Pantoja",
                        nombre=None, direccion="Calle 1", encargado="Ana",
                        nombre_completo="GBC PANTOJA")
    f2 = svc.actualizar_maestro(db, f, {"sucursal": "Villa Mella"}, usuario_id=7)
    assert f2.sucursal == "Villa Mella"
    assert f2.nombre_completo == "GBC VILLA MELLA"
    db.commit.assert_called_once()
