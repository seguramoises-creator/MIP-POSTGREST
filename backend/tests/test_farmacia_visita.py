"""Tests Farmacias — Tarea 6 (registro de visita a farmacia + guard F22).

Dos capas, mismo patrón que `test_farmacia_aprobacion_service.py` (servicio, con
dobles de Session) y `test_farmacias_router.py` (router, TestClient + overrides de
`get_current_active_user`/`get_db`).
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.models.usuario import Rol
from app.core.deps import get_current_active_user
from app.db.database import get_db
from app.api.v1.routers import farmacias as mod
from app.schemas.schemas_farmacia import VisitaFarmaciaRegistrar
from app.services import visita_farmacia_service as svc
from app.services import recalculo_service


# ─────────────────────────────────────────────────────────────────────────
# Capa servicio — registrar_visita (guard F22 + guard de ciclo abierto)
# ─────────────────────────────────────────────────────────────────────────

def _fake_db():
    db = MagicMock()
    db.refresh.side_effect = lambda obj: None
    return db


def _panel(**over):
    base = dict(id=1, vm_id=7, maestro_farmacia_id=50, estado_aprobacion="APROBADO")
    base.update(over)
    return SimpleNamespace(**base)


def _maestro(**over):
    base = dict(id=50, estado="ACTIVA")
    base.update(over)
    return SimpleNamespace(**base)


def _datos(**over):
    base = dict(comentario="Visita de rutina, todo en orden", hace_minutos=0,
                ejecutada=True, causa_no_visita=None, latitud=None, longitud=None)
    base.update(over)
    return VisitaFarmaciaRegistrar(**base)


def test_registrar_visita_farmacia_activa_panel_aprobado_ok(monkeypatch):
    db = _fake_db()
    panel = _panel()
    db.query.return_value.filter.return_value.first.return_value = _maestro()
    monkeypatch.setattr(svc, "ciclo_por_defecto", lambda db_, vm_id: 42)
    monkeypatch.setattr(recalculo_service, "validar_ciclo_abierto", lambda db_, cid: None)

    v = svc.registrar_visita(db, vm_id=7, panel=panel, datos=_datos(), usuario_id=9)

    assert v.vm_id == 7
    assert v.ciclo_id == 42
    assert v.farmacia_id == panel.id
    assert v.ejecutada is True
    assert v.registrado_por == 9
    db.add.assert_called_once()
    db.commit.assert_called_once()


def test_registrar_visita_farmacia_pendiente_aprobacion_f22(monkeypatch):
    db = _fake_db()
    panel = _panel(estado_aprobacion="PENDIENTE_ALTA")
    monkeypatch.setattr(svc, "ciclo_por_defecto", lambda db_, vm_id: 42)

    with pytest.raises(svc.PanelNoAprobadoError):
        svc.registrar_visita(db, vm_id=7, panel=panel, datos=_datos(), usuario_id=9)
    db.add.assert_not_called()


def test_registrar_visita_maestro_no_activa_f22(monkeypatch):
    db = _fake_db()
    panel = _panel(estado_aprobacion="APROBADO")
    db.query.return_value.filter.return_value.first.return_value = _maestro(estado="PENDIENTE_APROBACION")

    with pytest.raises(svc.PanelNoAprobadoError):
        svc.registrar_visita(db, vm_id=7, panel=panel, datos=_datos(), usuario_id=9)
    db.add.assert_not_called()


def test_registrar_visita_ciclo_cerrado_409_semantico(monkeypatch):
    db = _fake_db()
    panel = _panel()
    db.query.return_value.filter.return_value.first.return_value = _maestro()
    monkeypatch.setattr(svc, "ciclo_por_defecto", lambda db_, vm_id: 42)

    def _cerrado(db_, cid):
        raise recalculo_service.CicloCerradoError()
    monkeypatch.setattr(recalculo_service, "validar_ciclo_abierto", _cerrado)

    with pytest.raises(ValueError, match="cerrado"):
        svc.registrar_visita(db, vm_id=7, panel=panel, datos=_datos(), usuario_id=9)
    db.add.assert_not_called()


def test_registrar_visita_sin_ciclo_activo(monkeypatch):
    db = _fake_db()
    panel = _panel()
    db.query.return_value.filter.return_value.first.return_value = _maestro()
    monkeypatch.setattr(svc, "ciclo_por_defecto", lambda db_, vm_id: None)

    with pytest.raises(ValueError, match="ciclo activo"):
        svc.registrar_visita(db, vm_id=7, panel=panel, datos=_datos(), usuario_id=9)


# ─────────────────────────────────────────────────────────────────────────
# Capa servicio — foto (magic bytes + tope de tamaño)
# ─────────────────────────────────────────────────────────────────────────

_JPEG = b"\xff\xd8\xff" + b"0" * 20
_PNG = b"\x89PNG\r\n" + b"0" * 20


def test_guardar_foto_jpeg_ok():
    db = _fake_db()
    v = SimpleNamespace(id=1, foto=None, foto_mime=None)
    db.query.return_value.filter.return_value.first.return_value = v
    svc.guardar_foto_visita(db, 1, _JPEG, "image/jpeg")
    assert v.foto == _JPEG
    assert v.foto_mime == "image/jpeg"
    db.commit.assert_called_once()


def test_guardar_foto_png_ok():
    db = _fake_db()
    v = SimpleNamespace(id=1, foto=None, foto_mime=None)
    db.query.return_value.filter.return_value.first.return_value = v
    svc.guardar_foto_visita(db, 1, _PNG, "image/png")
    assert v.foto == _PNG


def test_guardar_foto_tipo_invalido_rechazada():
    db = _fake_db()
    with pytest.raises(ValueError, match="no es una imagen"):
        svc.guardar_foto_visita(db, 1, b"%PDF-1.4 no es una imagen", "application/pdf")


def test_guardar_foto_excede_tamano_rechazada():
    db = _fake_db()
    contenido = _JPEG + b"0" * (svc.MAX_FOTO_BYTES + 1)
    with pytest.raises(ValueError, match="tamaño máximo"):
        svc.guardar_foto_visita(db, 1, contenido, "image/jpeg")


def test_obtener_foto_visita_inexistente_none():
    db = _fake_db()
    db.query.return_value.filter.return_value.first.return_value = None
    assert svc.obtener_foto_visita(db, 999) is None


def test_obtener_foto_visita_ok():
    db = _fake_db()
    v = SimpleNamespace(foto=b"abc", foto_mime="image/jpeg")
    db.query.return_value.filter.return_value.first.return_value = v
    contenido, mime = svc.obtener_foto_visita(db, 1)
    assert contenido == b"abc"
    assert mime == "image/jpeg"


# ─────────────────────────────────────────────────────────────────────────
# Capa router — auto-scope (403 panel ajeno), F22 (409), ciclo cerrado (409), foto
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


def _db_con_panel(panel):
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = panel
    return db


def test_registrar_visita_panel_de_otro_vm_403():
    panel = _panel(vm_id=999)  # pertenece a otro VM
    db = _db_con_panel(panel)
    client = _client(U(Rol.REPRESENTANTE_MEDICO, rm_id=7), db=db)
    r = client.post("/api/v1/farmacias/1/visita", json={"comentario": "Visita de rutina hoy"})
    assert r.status_code == 403


def test_registrar_visita_f22_409_via_router(monkeypatch):
    panel = _panel(vm_id=7)
    db = _db_con_panel(panel)

    def _raise(*a, **k):
        raise mod.visita_svc.PanelNoAprobadoError(
            "Esta farmacia todavía no fue aprobada por tu Gerente de Distrito — "
            "no puedes registrarle visita.")
    monkeypatch.setattr(mod.visita_svc, "registrar_visita", _raise)

    client = _client(U(Rol.REPRESENTANTE_MEDICO, rm_id=7), db=db)
    r = client.post("/api/v1/farmacias/1/visita", json={"comentario": "Visita de rutina hoy"})
    assert r.status_code == 409


def test_registrar_visita_ciclo_cerrado_409_via_router(monkeypatch):
    panel = _panel(vm_id=7)
    db = _db_con_panel(panel)

    def _raise(*a, **k):
        raise ValueError("El ciclo está cerrado — solo lectura")
    monkeypatch.setattr(mod.visita_svc, "registrar_visita", _raise)

    client = _client(U(Rol.REPRESENTANTE_MEDICO, rm_id=7), db=db)
    r = client.post("/api/v1/farmacias/1/visita", json={"comentario": "Visita de rutina hoy"})
    assert r.status_code == 409


def test_registrar_visita_ok_via_router(monkeypatch):
    panel = _panel(vm_id=7)
    db = _db_con_panel(panel)
    creada = SimpleNamespace(id=10, vm_id=7, ciclo_id=42, farmacia_id=1, ejecutada=True, fecha_hora=None)
    monkeypatch.setattr(mod.visita_svc, "registrar_visita", lambda *a, **k: creada)

    client = _client(U(Rol.REPRESENTANTE_MEDICO, rm_id=7), db=db)
    r = client.post("/api/v1/farmacias/1/visita", json={"comentario": "Visita de rutina hoy"})
    assert r.status_code == 201
    body = r.json()
    assert body["id"] == 10
    assert body["farmacia_id"] == 1


def test_registrar_visita_rol_sin_permiso_403():
    # farmacia.panel: FINANZAS no tiene REGISTER
    client = _client(U(Rol.FINANZAS))
    r = client.post("/api/v1/farmacias/1/visita", json={"comentario": "Visita de rutina hoy"})
    assert r.status_code == 403


# ── Foto vía router ──────────────────────────────────────────────────────

def test_subir_foto_visita_farmacia_tipo_invalido_400(monkeypatch):
    def _raise(*a, **k):
        raise ValueError("El archivo no es una imagen JPEG/PNG válida")
    monkeypatch.setattr(mod.visita_svc, "guardar_foto_visita", _raise)

    client = _client(U(Rol.REPRESENTANTE_MEDICO, rm_id=7), db=MagicMock())
    r = client.post("/api/v1/farmacias/1/foto",
                    files={"archivo": ("x.pdf", b"%PDF-1.4", "application/pdf")})
    assert r.status_code == 400


def test_subir_foto_visita_farmacia_excede_tamano_400(monkeypatch):
    def _raise(*a, **k):
        raise ValueError("La foto excede el tamaño máximo (3 MB)")
    monkeypatch.setattr(mod.visita_svc, "guardar_foto_visita", _raise)

    client = _client(U(Rol.REPRESENTANTE_MEDICO, rm_id=7), db=MagicMock())
    r = client.post("/api/v1/farmacias/1/foto",
                    files={"archivo": ("x.jpg", _JPEG, "image/jpeg")})
    assert r.status_code == 400


def test_subir_foto_visita_farmacia_ok(monkeypatch):
    monkeypatch.setattr(mod.visita_svc, "guardar_foto_visita", lambda *a, **k: None)
    client = _client(U(Rol.REPRESENTANTE_MEDICO, rm_id=7), db=MagicMock())
    r = client.post("/api/v1/farmacias/1/foto",
                    files={"archivo": ("x.jpg", _JPEG, "image/jpeg")})
    assert r.status_code == 201


def test_obtener_foto_visita_farmacia_404_sin_foto(monkeypatch):
    monkeypatch.setattr(mod.visita_svc, "obtener_foto_visita", lambda *a, **k: None)
    client = _client(U(Rol.REPRESENTANTE_MEDICO, rm_id=7), db=MagicMock())
    r = client.get("/api/v1/farmacias/1/foto")
    assert r.status_code == 404


def test_obtener_foto_visita_farmacia_ok(monkeypatch):
    monkeypatch.setattr(mod.visita_svc, "obtener_foto_visita", lambda *a, **k: (b"abc", "image/jpeg"))
    client = _client(U(Rol.REPRESENTANTE_MEDICO, rm_id=7), db=MagicMock())
    r = client.get("/api/v1/farmacias/1/foto")
    assert r.status_code == 200
    assert r.content == b"abc"
    assert r.headers["content-type"] == "image/jpeg"
