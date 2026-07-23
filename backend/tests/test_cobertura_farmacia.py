"""Tests Farmacias — Tarea 7 (cobertura interna simple, coexiste con SFA).

Dobles de Session (`MagicMock` + `db.query.side_effect` por llamada a `db.query(...)`,
en el orden en que ocurren dentro de la función bajo prueba) — mismo patrón que
`test_farmacia_aprobacion_service.py`. Las filas ya vienen "pre-filtradas" como las
devolvería SQL real (la condición WHERE no se re-verifica en Python).
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.models.usuario import Rol
from app.core.deps import get_current_active_user
from app.db.database import get_db
from app.api.v1.routers import farmacias as mod
from app.services import cobertura_farmacia_service as svc


def _fake_db():
    return MagicMock()


class _Q:
    """Doble simple de Session.query(...).join(...).filter(...).all()/.distinct().count()."""

    def __init__(self, rows=None):
        self._rows = rows if rows is not None else []

    def join(self, *a, **k):
        return self

    def filter(self, *a, **k):
        return self

    def distinct(self, *a, **k):
        return self

    def all(self):
        return self._rows

    def count(self):
        return len(self._rows)


# ─────────────────────────────────────────────────────────────────────────
# cobertura_rm
# ─────────────────────────────────────────────────────────────────────────

def test_cobertura_correcta_panel_mixto():
    """4 farmacias APROBADAS en el panel; 3 con >=1 visita ejecutada en el ciclo -> 75%."""
    db = _fake_db()
    db.query.side_effect = [
        _Q(rows=[(1,), (2,), (3,), (4,)]),   # universo (panel APROBADO activo)
        _Q(rows=[(1,), (2,), (3,)]),          # farmacias visitadas (ejecutada=True, distinct)
    ]
    resultado = svc.cobertura_rm(db, vm_id=7, ciclo_id=42)
    assert resultado == {"visitadas": 3, "universo": 4, "cobertura_pct": 75.0}


def test_pendiente_no_cuenta_en_universo_ni_visitadas_f22():
    """F22: el panel tiene 3 farmacias, pero 1 está PENDIENTE_APROBACION — la consulta
    real de universo (`estado_aprobacion="APROBADO"`) la excluye, así que solo llegan 2
    filas simuladas aquí. Una visita a la farmacia pendiente (id=3) tampoco debe contar,
    porque el filtro `.in_(universo_ids)` la deja fuera del segundo query."""
    db = _fake_db()
    db.query.side_effect = [
        _Q(rows=[(1,), (2,)]),  # universo: solo las 2 APROBADAS (la id=3 PENDIENTE quedó fuera)
        _Q(rows=[(1,)]),         # visitadas: aunque hubo visita a la farmacia 3, no aparece aquí
    ]
    resultado = svc.cobertura_rm(db, vm_id=7, ciclo_id=42)
    assert resultado == {"visitadas": 1, "universo": 2, "cobertura_pct": 50.0}


def test_panel_vacio_cobertura_cero_sin_dividir_por_cero():
    db = _fake_db()
    db.query.side_effect = [
        _Q(rows=[]),  # universo vacío
    ]
    resultado = svc.cobertura_rm(db, vm_id=7, ciclo_id=42)
    assert resultado == {"visitadas": 0, "universo": 0, "cobertura_pct": 0.0}
    # No debe ni intentar el segundo query (universo vacío = corto-circuito).
    assert db.query.call_count == 1


def test_universo_filtra_por_maestro_activa():
    """Hallazgo menor 6: `_universo_ids` debe unir con `Farmacia` y filtrar
    `estado == "ACTIVA"` — una farmacia con panel APROBADO pero maestro INACTIVA
    (p.ej. dada de baja) no debe entrar al universo de cobertura."""
    db = MagicMock()
    db.query.return_value.join.return_value.filter.return_value.all.return_value = []

    svc._universo_ids(db, vm_id=7)

    db.query.return_value.join.assert_called_once()
    condiciones = db.query.return_value.join.return_value.filter.call_args[0]
    valores = [getattr(getattr(c, "right", None), "value", None) for c in condiciones]
    assert "ACTIVA" in valores


def test_visita_no_ejecutada_no_cuenta_como_visitada():
    """Una farmacia con panel APROBADO pero cuya única visita en el ciclo tiene
    `ejecutada=False` no debe contar: el query real filtra `ejecutada=True`, así que
    la simulamos devolviendo 0 filas visitadas pese a existir universo."""
    db = _fake_db()
    db.query.side_effect = [
        _Q(rows=[(1,)]),  # universo: 1 farmacia APROBADA
        _Q(rows=[]),        # visitadas: la visita existente tiene ejecutada=False -> excluida
    ]
    resultado = svc.cobertura_rm(db, vm_id=7, ciclo_id=42)
    assert resultado == {"visitadas": 0, "universo": 1, "cobertura_pct": 0.0}


# ─────────────────────────────────────────────────────────────────────────
# cobertura_equipo
# ─────────────────────────────────────────────────────────────────────────

def test_cobertura_equipo_agrega_por_vm(monkeypatch):
    db = _fake_db()
    vm7 = SimpleNamespace(id=7, nombre="VM Siete", gerente_id=100, activo=True)
    vm8 = SimpleNamespace(id=8, nombre="VM Ocho", gerente_id=100, activo=True)
    db.query.side_effect = [_Q(rows=[vm7, vm8])]

    # cobertura_rm se llama una vez por VM — se mockea directamente para aislar
    # la agregación de `cobertura_equipo` de la lógica interna ya probada arriba.
    llamadas = []

    def _fake_cobertura_rm(_db, vm_id, ciclo_id):
        llamadas.append((vm_id, ciclo_id))
        return {"visitadas": vm_id, "universo": 10, "cobertura_pct": vm_id * 10.0}

    monkeypatch.setattr(svc, "cobertura_rm", _fake_cobertura_rm)

    resultado = svc.cobertura_equipo(db, gerente_id=100, ciclo_id=42)

    assert llamadas == [(7, 42), (8, 42)]
    assert resultado == [
        {"vm_id": 7, "vm_nombre": "VM Siete", "visitadas": 7, "universo": 10, "cobertura_pct": 70.0},
        {"vm_id": 8, "vm_nombre": "VM Ocho", "visitadas": 8, "universo": 10, "cobertura_pct": 80.0},
    ]


def test_cobertura_equipo_sin_vms_lista_vacia():
    db = _fake_db()
    db.query.side_effect = [_Q(rows=[])]
    assert svc.cobertura_equipo(db, gerente_id=999, ciclo_id=42) == []


# ─────────────────────────────────────────────────────────────────────────
# Router — GET /farmacias/cobertura — auto-scope (VM→propio, GD→equipo, ADMIN→todo)
# ─────────────────────────────────────────────────────────────────────────

def U(rol, rm_id=None, gerente_id=None, id=1):
    return SimpleNamespace(rol=rol, rm_id=rm_id, gerente_id=gerente_id, id=id, activo=True)


def _client(user=None, db=None):
    app = FastAPI()
    app.include_router(mod.router, prefix="/api/v1")
    if user is not None:
        app.dependency_overrides[get_current_active_user] = lambda: user
    if db is not None:
        app.dependency_overrides[get_db] = lambda: db
    return TestClient(app, raise_server_exceptions=False)


def test_router_vm_ve_solo_su_propia_cobertura(monkeypatch):
    monkeypatch.setattr(svc, "cobertura_rm",
                        lambda db_, vm_id, ciclo_id: {"visitadas": 1, "universo": 2, "cobertura_pct": 50.0})
    client = _client(U(Rol.REPRESENTANTE_MEDICO, rm_id=7), db=MagicMock())
    r = client.get("/api/v1/farmacias/cobertura?ciclo_id=42")
    assert r.status_code == 200
    assert r.json() == {"visitadas": 1, "universo": 2, "cobertura_pct": 50.0}


def test_router_gd_sin_rm_id_ve_su_equipo(monkeypatch):
    monkeypatch.setattr(svc, "cobertura_equipo",
                        lambda db_, gerente_id, ciclo_id: [{"vm_id": 7, "cobertura_pct": 50.0}])
    client = _client(U(Rol.GERENTE_DISTRITO, gerente_id=100), db=MagicMock())
    r = client.get("/api/v1/farmacias/cobertura?ciclo_id=42")
    assert r.status_code == 200
    assert r.json() == {"equipo": [{"vm_id": 7, "cobertura_pct": 50.0}]}


def test_router_gd_sin_gerente_id_403():
    client = _client(U(Rol.GERENTE_DISTRITO, gerente_id=None), db=MagicMock())
    r = client.get("/api/v1/farmacias/cobertura?ciclo_id=42")
    assert r.status_code == 403


def test_router_gd_rm_ajeno_403():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(id=9, gerente_id=999)
    client = _client(U(Rol.GERENTE_DISTRITO, gerente_id=100), db=db)
    r = client.get("/api/v1/farmacias/cobertura?ciclo_id=42&rm_id=9")
    assert r.status_code == 403


def test_router_admin_sin_filtrar_agrega_todos_los_distritos(monkeypatch):
    db = MagicMock()
    # Hallazgo menor 7: ahora filtra Gerente.tipo == "DISTRITO" antes de .all().
    db.query.return_value.filter.return_value.all.return_value = [
        SimpleNamespace(id=1, tipo="DISTRITO"), SimpleNamespace(id=2, tipo="DISTRITO")]
    monkeypatch.setattr(svc, "cobertura_equipo",
                        lambda db_, gerente_id, ciclo_id: [{"vm_id": gerente_id, "cobertura_pct": 0.0}])
    client = _client(U(Rol.ADMIN), db=db)
    r = client.get("/api/v1/farmacias/cobertura?ciclo_id=42")
    assert r.status_code == 200
    assert r.json() == {"equipo": [{"vm_id": 1, "cobertura_pct": 0.0}, {"vm_id": 2, "cobertura_pct": 0.0}]}


def test_router_rol_sin_permiso_403():
    client = _client(U(Rol.FINANZAS))
    r = client.get("/api/v1/farmacias/cobertura?ciclo_id=42")
    assert r.status_code == 403
