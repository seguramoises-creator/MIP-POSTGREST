"""RBAC Fase 1 — T7: endpoint /authz/me/permisos + /authz/matriz.

Se monta un FastAPI mínimo con SOLO el router authz y se sobreescribe get_current_active_user
via dependency_overrides (no requiere BD ni login). require_roles depende de
get_current_active_user, por lo que el override también controla el guard de /authz/matriz.
"""
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.models.usuario import Rol
from app.core.authz.constantes import RECURSOS
from app.core.deps import get_current_active_user
from app.db.database import get_db
from app.core.authz import runtime
from app.api.v1.routers.authz import router as authz_router


class _FakeQ:
    def all(self): return []
    def scalar(self): return None


class _FakeDB:
    """Sesión vacía: sin filas de permisos → la matriz cae a los valores de fábrica."""
    def query(self, *a, **k): return _FakeQ()
    def close(self): pass


def _app(user):
    # La matriz editable lee de BD; con la sesión vacía el runtime cae a fábrica (matrix.py).
    runtime.invalidar()
    app = FastAPI()
    app.include_router(authz_router, prefix="/api/v1")
    app.dependency_overrides[get_current_active_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: _FakeDB()
    return TestClient(app)


def U(rol, rm_id=None, gerente_id=None):
    return SimpleNamespace(rol=rol, rm_id=rm_id, gerente_id=gerente_id, id=1)


def test_me_permisos_rm():
    client = _app(U(Rol.REPRESENTANTE_MEDICO, rm_id=5))
    r = client.get("/api/v1/authz/me/permisos")
    assert r.status_code == 200
    data = r.json()
    assert data["rol"] == "REPRESENTANTE_MEDICO"
    # puede registrar su propia visita (register own ⇒ read own)
    assert data["permisos"]["visita.registrar"]["register"] == "own"
    assert data["permisos"]["visita.registrar"]["read"] == "own"
    # no ve config.usuarios ni exporta
    assert "config.usuarios" not in data["permisos"]
    assert "exportacion" not in data["permisos"]


def test_me_permisos_analista_exporta_no_escribe():
    client = _app(U(Rol.ANALISTA_DATOS))
    data = client.get("/api/v1/authz/me/permisos").json()["permisos"]
    assert data["exportacion"]["export"] == "all"
    # export efectivo sobre un módulo que lee (all) = all
    assert data["dashboard.ejecutivo"]["export_efectivo"] == "all"
    # no escribe en ningún lado
    for recurso, caps in data.items():
        assert "register" not in caps and "configure" not in caps
        assert "approve" not in caps and "admin" not in caps


def test_me_permisos_medico_sin_comercial():
    client = _app(U(Rol.GERENTE_MEDICO))
    data = client.get("/api/v1/authz/me/permisos").json()["permisos"]
    assert "productividad.comercial" not in data
    assert "ranking.rkt" not in data
    assert "costoroi.ver" not in data


def test_matriz_solo_admin():
    # no-admin → 403
    assert _app(U(Rol.REPRESENTANTE_MEDICO)).get("/api/v1/authz/matriz").status_code == 403
    # admin → 200 con el catálogo completo de recursos
    r = _app(U(Rol.ADMIN)).get("/api/v1/authz/matriz")
    assert r.status_code == 200
    assert len(r.json()["recursos"]) == len(RECURSOS)
