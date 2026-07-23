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
# estado_visita_panel — pestaña Farmacia de Registrar Visita (jul-2026): badge
# Cadena/Independiente + estado (hoy/ciclo) + comentario de la visita anterior,
# como la pestaña de Médico.
# ─────────────────────────────────────────────────────────────────────────

from datetime import datetime, timezone, timedelta


def _visita_ejecutada(**over):
    base = dict(farmacia_id=1, ejecutada=True, fecha_hora=datetime.now(timezone.utc),
                ciclo_id=42, comentario=None)
    base.update(over)
    return SimpleNamespace(**base)


def test_estado_visita_panel_sin_panel_ids_devuelve_vacio():
    db = _fake_db()
    assert svc.estado_visita_panel(db, vm_id=7, ciclo_id=42, panel_ids=[]) == {}


def test_estado_visita_panel_hoy_ciclo_y_ultimo_comentario():
    db = _fake_db()
    ahora = datetime.now(timezone.utc)
    ayer = ahora - timedelta(days=1)
    # Ordenadas DESC por fecha_hora (como hace la query real): la más reciente primero.
    filas = [
        _visita_ejecutada(farmacia_id=1, fecha_hora=ahora, ciclo_id=42, comentario="Hoy mismo"),
        _visita_ejecutada(farmacia_id=1, fecha_hora=ayer, ciclo_id=41, comentario="Ayer"),
        _visita_ejecutada(farmacia_id=2, fecha_hora=ayer, ciclo_id=42, comentario="Otra farmacia"),
    ]
    db.query.return_value.filter.return_value.order_by.return_value.all.return_value = filas

    estados = svc.estado_visita_panel(db, vm_id=7, ciclo_id=42, panel_ids=[1, 2, 3])

    # farmacia 1: visitada hoy Y en el ciclo 42 (la fila de hoy); comentario = el de la más reciente.
    assert estados[1] == {"visitada_hoy": True, "visitada_ciclo": True, "ultimo_comentario": "Hoy mismo"}
    # farmacia 2: NO hoy (fue ayer), pero SÍ en el ciclo 42.
    assert estados[2] == {"visitada_hoy": False, "visitada_ciclo": True, "ultimo_comentario": "Otra farmacia"}
    # farmacia 3: sin visitas -> no aparece en el mapa (el llamador debe usar defaults).
    assert 3 not in estados


def test_estado_visita_panel_farmacia_solo_en_otro_ciclo():
    db = _fake_db()
    ayer = datetime.now(timezone.utc) - timedelta(days=5)
    db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [
        _visita_ejecutada(farmacia_id=9, fecha_hora=ayer, ciclo_id=41, comentario="Ciclo anterior"),
    ]

    estados = svc.estado_visita_panel(db, vm_id=7, ciclo_id=42, panel_ids=[9])

    assert estados[9]["visitada_hoy"] is False
    assert estados[9]["visitada_ciclo"] is False   # el ciclo pedido es el 42, la visita fue en el 41
    assert estados[9]["ultimo_comentario"] == "Ciclo anterior"


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


# ── Foto vía router — scope de dueño (IDOR, hallazgo crítico 1) ──────────────
# `_cargar_visita_farmacia_scoped` (farmacias.py) resuelve la visita por `visita_id`
# y verifica que quien pide subir/leer la foto es su dueño (VM), su GD, o ADMIN.
# Antes `subir_foto_visita_farmacia`/`obtener_foto_visita_farmacia` NO verificaban
# nada: cualquier VM autenticado podía leer/sobrescribir la foto de OTRO VM con solo
# adivinar el `visita_id`.

def _visita_farmacia(**over):
    base = dict(id=1, vm_id=7)
    base.update(over)
    return SimpleNamespace(**base)


def test_subir_foto_visita_farmacia_tipo_invalido_400(monkeypatch):
    def _raise(*a, **k):
        raise ValueError("El archivo no es una imagen JPEG/PNG válida")
    monkeypatch.setattr(mod.visita_svc, "guardar_foto_visita", _raise)

    db = _db_con_panel(_visita_farmacia(vm_id=7))
    client = _client(U(Rol.REPRESENTANTE_MEDICO, rm_id=7), db=db)
    r = client.post("/api/v1/farmacias/1/foto",
                    files={"archivo": ("x.pdf", b"%PDF-1.4", "application/pdf")})
    assert r.status_code == 400


def test_subir_foto_visita_farmacia_excede_tamano_400(monkeypatch):
    def _raise(*a, **k):
        raise ValueError("La foto excede el tamaño máximo (3 MB)")
    monkeypatch.setattr(mod.visita_svc, "guardar_foto_visita", _raise)

    db = _db_con_panel(_visita_farmacia(vm_id=7))
    client = _client(U(Rol.REPRESENTANTE_MEDICO, rm_id=7), db=db)
    r = client.post("/api/v1/farmacias/1/foto",
                    files={"archivo": ("x.jpg", _JPEG, "image/jpeg")})
    assert r.status_code == 400


def test_subir_foto_visita_farmacia_ok(monkeypatch):
    monkeypatch.setattr(mod.visita_svc, "guardar_foto_visita", lambda *a, **k: None)
    db = _db_con_panel(_visita_farmacia(vm_id=7))
    client = _client(U(Rol.REPRESENTANTE_MEDICO, rm_id=7), db=db)
    r = client.post("/api/v1/farmacias/1/foto",
                    files={"archivo": ("x.jpg", _JPEG, "image/jpeg")})
    assert r.status_code == 201


def test_obtener_foto_visita_farmacia_404_sin_foto(monkeypatch):
    monkeypatch.setattr(mod.visita_svc, "obtener_foto_visita", lambda *a, **k: None)
    db = _db_con_panel(_visita_farmacia(vm_id=7))
    client = _client(U(Rol.REPRESENTANTE_MEDICO, rm_id=7), db=db)
    r = client.get("/api/v1/farmacias/1/foto")
    assert r.status_code == 404


def test_obtener_foto_visita_farmacia_ok(monkeypatch):
    monkeypatch.setattr(mod.visita_svc, "obtener_foto_visita", lambda *a, **k: (b"abc", "image/jpeg"))
    db = _db_con_panel(_visita_farmacia(vm_id=7))
    client = _client(U(Rol.REPRESENTANTE_MEDICO, rm_id=7), db=db)
    r = client.get("/api/v1/farmacias/1/foto")
    assert r.status_code == 200
    assert r.content == b"abc"
    assert r.headers["content-type"] == "image/jpeg"


def test_visita_farmacia_inexistente_404(monkeypatch):
    db = _db_con_panel(None)
    client = _client(U(Rol.REPRESENTANTE_MEDICO, rm_id=7), db=db)
    r = client.get("/api/v1/farmacias/999/foto")
    assert r.status_code == 404


def test_subir_foto_visita_farmacia_de_otro_vm_403(monkeypatch):
    """VM_A (rm_id=7) intenta subir la foto de una visita de VM_B (vm_id=999)."""
    guardar = MagicMock()
    monkeypatch.setattr(mod.visita_svc, "guardar_foto_visita", guardar)
    db = _db_con_panel(_visita_farmacia(vm_id=999))
    client = _client(U(Rol.REPRESENTANTE_MEDICO, rm_id=7), db=db)
    r = client.post("/api/v1/farmacias/1/foto",
                    files={"archivo": ("x.jpg", _JPEG, "image/jpeg")})
    assert r.status_code == 403
    guardar.assert_not_called()


def test_obtener_foto_visita_farmacia_de_otro_vm_403(monkeypatch):
    """VM_A (rm_id=7) intenta leer la foto de una visita de VM_B (vm_id=999)."""
    obtener = MagicMock(return_value=(b"abc", "image/jpeg"))
    monkeypatch.setattr(mod.visita_svc, "obtener_foto_visita", obtener)
    db = _db_con_panel(_visita_farmacia(vm_id=999))
    client = _client(U(Rol.REPRESENTANTE_MEDICO, rm_id=7), db=db)
    r = client.get("/api/v1/farmacias/1/foto")
    assert r.status_code == 403
    obtener.assert_not_called()


def test_subir_foto_visita_farmacia_admin_ok_aunque_sea_de_otro_vm(monkeypatch):
    monkeypatch.setattr(mod.visita_svc, "guardar_foto_visita", lambda *a, **k: None)
    db = _db_con_panel(_visita_farmacia(vm_id=999))
    client = _client(U(Rol.ADMIN), db=db)
    r = client.post("/api/v1/farmacias/1/foto",
                    files={"archivo": ("x.jpg", _JPEG, "image/jpeg")})
    assert r.status_code == 201


def test_obtener_foto_visita_farmacia_admin_ok_aunque_sea_de_otro_vm(monkeypatch):
    monkeypatch.setattr(mod.visita_svc, "obtener_foto_visita", lambda *a, **k: (b"abc", "image/jpeg"))
    db = _db_con_panel(_visita_farmacia(vm_id=999))
    client = _client(U(Rol.ADMIN), db=db)
    r = client.get("/api/v1/farmacias/1/foto")
    assert r.status_code == 200
    assert r.content == b"abc"


def _db_con_visita_y_rm(visita, rm_gerente_id):
    """FakeDB dispatchado por modelo: FactVisitaFarmacia -> la visita; RepresentanteMedico
    -> un RM del gerente indicado (para el chequeo de equipo del GD)."""
    db = MagicMock()
    rm = SimpleNamespace(id=visita.vm_id, gerente_id=rm_gerente_id)

    def _query(modelo):
        q = MagicMock()
        nombre = getattr(modelo, "__name__", None)
        if nombre == "FactVisitaFarmacia":
            q.filter.return_value.first.return_value = visita
        elif nombre == "RepresentanteMedico":
            q.filter.return_value.first.return_value = rm
        return q
    db.query.side_effect = _query
    return db


def test_gd_lee_foto_de_su_equipo_ok(monkeypatch):
    monkeypatch.setattr(mod.visita_svc, "obtener_foto_visita", lambda *a, **k: (b"abc", "image/jpeg"))
    visita = _visita_farmacia(vm_id=7)
    db = _db_con_visita_y_rm(visita, rm_gerente_id=3)
    client = _client(U(Rol.GERENTE_DISTRITO, gerente_id=3), db=db)
    r = client.get("/api/v1/farmacias/1/foto")
    assert r.status_code == 200


def test_gd_no_lee_foto_de_otro_equipo_403(monkeypatch):
    obtener = MagicMock(return_value=(b"abc", "image/jpeg"))
    monkeypatch.setattr(mod.visita_svc, "obtener_foto_visita", obtener)
    visita = _visita_farmacia(vm_id=7)
    db = _db_con_visita_y_rm(visita, rm_gerente_id=999)  # el VM es de OTRO gerente
    client = _client(U(Rol.GERENTE_DISTRITO, gerente_id=3), db=db)
    r = client.get("/api/v1/farmacias/1/foto")
    assert r.status_code == 403
    obtener.assert_not_called()
