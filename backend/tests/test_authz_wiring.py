"""RBAC Fase 2 — wiring de guards en endpoints reales (ruta de DENEGACIÓN, sin BD).

Verifica que el guard de la matriz rechaza al rol denegado ANTES de tocar la BD. Se sobreescribe
get_current_active_user; el guard require() lo usa. La ruta permitida haría queries (necesita BD),
así que aquí solo se comprueba el 403 del firewall/denegación por defecto.
"""
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.models.usuario import Rol
from app.core.deps import get_current_active_user


def _client(router, user):
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_current_active_user] = lambda: user
    return TestClient(app, raise_server_exceptions=False)


def U(rol, rm_id=None, gerente_id=None):
    return SimpleNamespace(rol=rol, rm_id=rm_id, gerente_id=gerente_id, id=1)


def test_productividad_firewall_medico_403():
    from app.api.v1.routers.productividad import router
    r = _client(router, U(Rol.GERENTE_MEDICO)).get("/api/v1/productividad")
    assert r.status_code == 403


def test_productividad_resumen_firewall_medico_403():
    from app.api.v1.routers.productividad import router
    r = _client(router, U(Rol.GERENTE_MEDICO)).get("/api/v1/productividad/resumen")
    assert r.status_code == 403
