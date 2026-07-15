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
    assert db.add.call_count == 2  # médico + registro de auditoría
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
    assert db.add.call_count == 2  # médico + registro de auditoría
    db.commit.assert_called_once()
    db.refresh.assert_called_once()
    assert m.estado_validacion == "APROBADO"
    assert m.origen == "MANUAL"


# ── detectar_duplicados: dedup real (dura/blanda), sin monkeypatch ──────────────
from types import SimpleNamespace


class _Q:
    """Doble de Session.query(...).filter(...).all() controlado por fila."""
    def __init__(self, rows): self._rows = rows
    def filter(self, *a, **k): return self
    def all(self): return self._rows


def _cand(**kw):
    base = dict(id=1, nombre="X", codigo=None, exequatur=None, cedula=None,
                centro_medico_id=None, provincia_id=None, telefono=None)
    base.update(kw)
    return SimpleNamespace(**base)


def test_detectar_duro_por_exequatur():
    db = MagicMock()
    db.query.side_effect = [_Q([_cand(id=7, exequatur="EXQ-1")])]  # 1 query: la de duros
    res = svc.detectar_duplicados(db, "DO", exequatur="EXQ-1")
    assert [d["id"] for d in res["duros"]] == [7]
    assert res["blandos"] == []


def test_detectar_blando_matchea_pese_a_acentos():
    db = MagicMock()
    # Sin exequátur/cédula → no hay query de duros; solo la de blandos.
    db.query.side_effect = [_Q([_cand(id=9, nombre="JOSÉ PEÑA", centro_medico_id=5)])]
    res = svc.detectar_duplicados(db, "DO", nombre="Jose Pena", centro_medico_id=5)
    assert [d["id"] for d in res["blandos"]] == [9]   # "JOSÉ PEÑA" == "JOSE PENA" normalizado
    assert res["duros"] == []


def test_detectar_blando_requiere_ubicacion():
    db = MagicMock()
    # Sin centro ni provincia (y sin exequátur/cédula) → no se consulta nada.
    res = svc.detectar_duplicados(db, "DO", nombre="Jose Pena")
    assert res["blandos"] == [] and res["duros"] == []
    db.query.assert_not_called()


# ── importar_excel: upsert idempotente por llave dura ───────────────────────────
def test_importar_upsert(monkeypatch):
    llamadas = {"crear": []}
    existentes = {"E1": SimpleNamespace(id=1, exequatur="E1", cedula=None, codigo=None, telefono="OLD")}
    monkeypatch.setattr(svc, "_resolver_por_llave_dura",
        lambda db, pais, exequatur=None, cedula=None, codigo=None: existentes.get(exequatur))
    monkeypatch.setattr(svc, "detectar_duplicados", lambda *a, **k: {"duros": [], "blandos": []})
    monkeypatch.setattr(svc, "crear_maestro",
        lambda db, pais, datos, **k: (llamadas["crear"].append(datos) or SimpleNamespace(id=99)))
    def _act(db, m, campos, uid=None):
        for k2, v in campos.items(): setattr(m, k2, v)
        return m
    monkeypatch.setattr(svc, "actualizar_maestro", _act)

    filas = [
        {"nombre": "JUAN PEREZ", "exequatur": "E1", "telefono": "NUEVO"},  # existe → actualiza
        {"nombre": "MARIA LOPEZ", "exequatur": "E2"},                       # no existe → crea
    ]
    res = svc.importar_excel(MagicMock(), "DO", filas)
    assert res["actualizados"] == 1 and res["creados"] == 1 and res["errores"] == []
    assert existentes["E1"].telefono == "NUEVO"          # teléfono sincronizado, no duplicado
    assert llamadas["crear"][0]["exequatur"] == "E2"     # el nuevo se creó


def test_importar_fila_sin_nombre_es_error(monkeypatch):
    monkeypatch.setattr(svc, "_resolver_por_llave_dura", lambda *a, **k: None)
    monkeypatch.setattr(svc, "detectar_duplicados", lambda *a, **k: {"duros": [], "blandos": []})
    monkeypatch.setattr(svc, "crear_maestro", lambda *a, **k: SimpleNamespace(id=1))
    res = svc.importar_excel(MagicMock(), "DO", [{"nombre": ""}, {"exequatur": "X"}])
    assert res["creados"] == 0 and len(res["errores"]) == 2
