"""RBAC Fase 2 — dependencies require()/autorizar() + roles legacy en el endpoint de permisos."""
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient

from app.models.usuario import Rol
from app.core.deps import get_current_active_user
from app.core.authz.constantes import Accion, Recurso, Alcance
from app.core.authz.deps import require, autorizar, Autorizacion


def _client(user, dep):
    app = FastAPI()

    @app.get("/probe")
    def probe(res=Depends(dep)):
        if isinstance(res, Autorizacion):
            return {"rol": res.usuario.rol.value, "alcance": res.alcance.value}
        return {"rol": res.rol.value}

    app.dependency_overrides[get_current_active_user] = lambda: user
    return TestClient(app)


def U(rol):
    return SimpleNamespace(rol=rol, rm_id=1, gerente_id=1, id=1)


def test_require_permite_y_deniega():
    dep = require(Accion.REGISTER, Recurso.VISITA_REGISTRAR)
    assert _client(U(Rol.REPRESENTANTE_MEDICO), dep).get("/probe").status_code == 200
    assert _client(U(Rol.GERENTE_DISTRITO), dep).get("/probe").status_code == 403


def test_autorizar_devuelve_alcance():
    dep = autorizar(Accion.READ, Recurso.PRODUCTIVIDAD_COMERCIAL)
    r = _client(U(Rol.GERENTE_DISTRITO), dep).get("/probe")
    assert r.status_code == 200
    assert r.json()["alcance"] == "team"


def test_capacitacion_conserva_examenes():
    # CAPACITACION (fila propia) conserva la configuración de exámenes
    dep = require(Accion.CONFIGURE, Recurso.EXAMEN_CONFIGURAR)
    assert _client(U(Rol.CAPACITACION), dep).get("/probe").status_code == 200


def test_consulta_lee_pero_no_exporta():
    from app.core.authz import engine
    consulta = U(Rol.CONSULTA)
    assert engine.can(consulta, Accion.READ, Recurso.DASHBOARD_EJECUTIVO) == Alcance.ALL
    assert engine.can(consulta, Accion.EXPORT, Recurso.EXPORTACION) is None


def test_dir_comercial_lee_y_exporta():
    from app.core.authz import engine
    dirc = U(Rol.DIR_COMERCIAL)
    assert engine.can(dirc, Accion.READ, Recurso.RANKING_RKT) == Alcance.ALL
    assert engine.can(dirc, Accion.EXPORT, Recurso.EXPORTACION) == Alcance.ALL
