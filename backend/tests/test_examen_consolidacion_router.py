"""Ronda de correcciones 1 (Tarea 4): el router de exámenes debe traducir
`FuenteAjenaError` a 409, no dejar que caiga en el handler genérico de `main.py`.

Sigue el patrón de `test_authz_wiring.py` — router aislado en una app mínima,
solo se sobreescribe `get_current_active_user`; no se sobreescribe `get_db`
porque el camino de la prueba nunca llega a ejecutar una query real (el guard
RBAC cae al fallback de fábrica sin BD, y `consolidar_ciclo` se monkeypatchea
para lanzar antes de tocar la sesión).
"""
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.deps import get_current_active_user
from app.models.usuario import Rol
from app.services import fuente_indicador_service as fuentes


def _client(router, user):
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_current_active_user] = lambda: user
    return TestClient(app, raise_server_exceptions=False)


def U(rol, rm_id=None, gerente_id=None):
    return SimpleNamespace(rol=rol, rm_id=rm_id, gerente_id=gerente_id, id=1)


def test_consolidar_traduce_fuente_ajena_a_409(monkeypatch):
    from app.api.v1.routers.examenes import router
    from app.services import examen_consolidacion_service as cons

    def _raise(db, ciclo_id, pais_codigo, usuario_id):
        raise fuentes.FuenteAjenaError(pais_codigo, fuentes.INDICADOR_CONOCIMIENTOS,
                                       fuentes.FUENTE_CAPTURA_MANUAL, fuentes.FUENTE_EXAMEN_VISTA)

    monkeypatch.setattr(cons, "consolidar_ciclo", _raise)

    r = _client(router, U(Rol.ADMIN)).post(
        "/api/v1/examenes/consolidacion/consolidar",
        json={"ciclo_id": 7, "pais_codigo": "DO"})

    assert r.status_code == 409
    cuerpo = r.json()["detail"]
    # El mensaje de FuenteAjenaError nombra al dueño real: es lo que el
    # operador de Capacitación necesita para saber qué cambiar y dónde.
    assert fuentes.FUENTE_CAPTURA_MANUAL in cuerpo
    assert "DO" in cuerpo
