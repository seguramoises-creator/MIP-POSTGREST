"""Tests Farmacias — Tarea 5 (router /farmacias + RBAC).

Convención del proyecto (ver test_authz_wiring.py / test_authz_endpoint.py): se monta un
FastAPI mínimo con SOLO el router de Farmacias y se sobreescribe `get_current_active_user`
(RBAC/auto-scope, sin BD) y, cuando la ruta sí necesita datos, `get_db` con un doble
(`MagicMock`/`SimpleNamespace`) o con la capa de servicio monkeypencheada — mismo patrón que
`test_farmacia_aprobacion_service.py`.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.models.usuario import Rol
from app.core.deps import get_current_active_user
from app.db.database import get_db
from app.api.v1.routers import farmacias as mod
from app.services import maestro_farmacia_service as maestro_svc


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


# ─────────────────────────────────────────────────────────────────────────
# 401 sin token — app real completa (sin overrides), el guard de JWT corta antes de la BD
# ─────────────────────────────────────────────────────────────────────────

def test_sin_token_401():
    from app.main import app
    client = TestClient(app, raise_server_exceptions=False)
    r = client.get("/api/v1/farmacias/panel")
    assert r.status_code == 401


# ─────────────────────────────────────────────────────────────────────────
# 403 por rol equivocado (matriz)
# ─────────────────────────────────────────────────────────────────────────

def test_finanzas_no_lee_panel_403():
    # farmacia.panel deniega a FINANZAS
    client = _client(U(Rol.FINANZAS))
    r = client.get("/api/v1/farmacias/maestro/buscar",
                   params={"pais_codigo": "DO", "cadena": "X", "sucursal": "Y"})
    assert r.status_code == 403


def test_gd_no_administra_maestro_directo_403():
    # farmacia.maestro es SOLO GERENTE_PRODUCTIVIDAD + ADMIN
    client = _client(U(Rol.GERENTE_DISTRITO, gerente_id=1))
    r = client.get("/api/v1/farmacias/maestro")
    assert r.status_code == 403


def test_rm_no_puede_aprobar_403():
    # farmacia.aprobar es SOLO GERENTE_DISTRITO (team) + ADMIN
    client = _client(U(Rol.REPRESENTANTE_MEDICO, rm_id=7))
    r = client.post("/api/v1/farmacias/aprobacion/1/aprobar")
    assert r.status_code == 403


def test_marca_no_registra_en_panel_403():
    # farmacia.panel: MARCA solo tiene READ (no REGISTER) -> no puede /panel/crear
    client = _client(U(Rol.GERENTE_MARCA))
    r = client.post("/api/v1/farmacias/panel/crear", json={"direccion": "Calle 1", "encargado": "Ana"})
    assert r.status_code == 403


def test_gerente_productividad_administra_maestro_pasa_guard():
    # farmacia.maestro: GERENTE_PRODUCTIVIDAD SÍ (CFG) -> el guard RBAC no lo bloquea
    # (puede fallar más adelante por falta de BD real, pero no con 403/401).
    db = MagicMock()
    db.query.return_value.order_by.return_value.all.return_value = []
    client = _client(U(Rol.GERENTE_PRODUCTIVIDAD), db=db)
    r = client.get("/api/v1/farmacias/maestro")
    assert r.status_code == 200


# ─────────────────────────────────────────────────────────────────────────
# POST /panel/crear — bloqueantes F23/F24 -> 422 (mensaje exacto del servicio)
# ─────────────────────────────────────────────────────────────────────────

def test_panel_crear_sin_direccion_422(monkeypatch):
    def _raise(*a, **k):
        raise ValueError("Debe completar la dirección de la farmacia para poder grabarla.")
    monkeypatch.setattr(mod.aprobacion_svc, "solicitar_crear", _raise)

    client = _client(U(Rol.REPRESENTANTE_MEDICO, rm_id=7), db=MagicMock())
    r = client.post("/api/v1/farmacias/panel/crear", json={"direccion": "", "encargado": "Ana"})
    assert r.status_code == 422
    assert "dirección" in r.json()["detail"]


def test_panel_crear_sin_encargado_422(monkeypatch):
    def _raise(*a, **k):
        raise ValueError("Debe indicar el nombre del encargado para poder grabar la farmacia.")
    monkeypatch.setattr(mod.aprobacion_svc, "solicitar_crear", _raise)

    client = _client(U(Rol.REPRESENTANTE_MEDICO, rm_id=7), db=MagicMock())
    r = client.post("/api/v1/farmacias/panel/crear", json={"direccion": "Calle 1", "encargado": ""})
    assert r.status_code == 422
    assert "encargado" in r.json()["detail"]


# ─────────────────────────────────────────────────────────────────────────
# POST /panel/crear — duplicado duro -> 409
# ─────────────────────────────────────────────────────────────────────────

def test_panel_crear_duplicado_duro_409(monkeypatch):
    def _raise(*a, **k):
        raise maestro_svc.DuplicadoDuroError([{"id": 5, "nombre_completo": "GBC PANTOJA"}])
    monkeypatch.setattr(mod.aprobacion_svc, "solicitar_crear", _raise)

    client = _client(U(Rol.REPRESENTANTE_MEDICO, rm_id=7), db=MagicMock())
    r = client.post("/api/v1/farmacias/panel/crear",
                    json={"direccion": "Calle 1", "encargado": "Ana", "cadena": "GBC", "sucursal": "Pantoja"})
    assert r.status_code == 409


def test_panel_agregar_ya_en_panel_409(monkeypatch):
    def _raise(*a, **k):
        raise ValueError("Esta farmacia ya está en tu panel.")
    monkeypatch.setattr(mod.aprobacion_svc, "solicitar_agregar_al_panel", _raise)

    client = _client(U(Rol.REPRESENTANTE_MEDICO, rm_id=7), db=MagicMock())
    r = client.post("/api/v1/farmacias/panel/agregar", json={"maestro_farmacia_id": 50})
    assert r.status_code == 409


# ─────────────────────────────────────────────────────────────────────────
# Aprobar/rechazar por GD — OK; rechazar sin motivo -> 400
# ─────────────────────────────────────────────────────────────────────────

def _panel_pendiente(**over):
    base = dict(id=1, vm_id=7, maestro_farmacia_id=50, estado_aprobacion="PENDIENTE_ALTA",
                fecha_solicitud=None, fecha_aprobacion=None, motivo=None)
    base.update(over)
    return SimpleNamespace(**base)


def _db_con_panel_y_rm(panel, rm_gerente_id):
    """FakeDB: primera consulta (FarmaciaVisita) devuelve el panel; la de RepresentanteMedico
    (usada por _verificar_alcance_gd/_panel_del_gd) devuelve un RM de ese gerente."""
    db = MagicMock()
    rm = SimpleNamespace(id=panel.vm_id, gerente_id=rm_gerente_id)

    def _query(modelo):
        q = MagicMock()
        if modelo.__name__ == "FarmaciaVisita":
            q.filter.return_value.first.return_value = panel
        elif modelo.__name__ == "RepresentanteMedico":
            q.filter.return_value.first.return_value = rm
        return q
    db.query.side_effect = _query
    return db


def test_gd_aprueba_solicitud_de_su_equipo_ok(monkeypatch):
    panel = _panel_pendiente()
    db = _db_con_panel_y_rm(panel, rm_gerente_id=3)
    aprobado = _panel_pendiente(estado_aprobacion="APROBADO")
    monkeypatch.setattr(mod.aprobacion_svc, "aprobar", lambda db_, panel_id, usuario_id=None: aprobado)

    client = _client(U(Rol.GERENTE_DISTRITO, gerente_id=3), db=db)
    r = client.post("/api/v1/farmacias/aprobacion/1/aprobar")
    assert r.status_code == 200
    assert r.json()["estado_aprobacion"] == "APROBADO"


def test_gd_no_puede_aprobar_solicitud_de_otro_equipo_403():
    panel = _panel_pendiente()
    db = _db_con_panel_y_rm(panel, rm_gerente_id=99)  # el VM pertenece a OTRO gerente

    client = _client(U(Rol.GERENTE_DISTRITO, gerente_id=3), db=db)
    r = client.post("/api/v1/farmacias/aprobacion/1/aprobar")
    assert r.status_code == 403


def test_gd_rechaza_con_motivo_ok(monkeypatch):
    panel = _panel_pendiente()
    db = _db_con_panel_y_rm(panel, rm_gerente_id=3)
    rechazado = _panel_pendiente(estado_aprobacion="RECHAZADO", motivo="Dirección incompleta")
    monkeypatch.setattr(mod.aprobacion_svc, "rechazar",
                        lambda db_, panel_id, motivo, usuario_id=None: rechazado)

    client = _client(U(Rol.GERENTE_DISTRITO, gerente_id=3), db=db)
    r = client.post("/api/v1/farmacias/aprobacion/1/rechazar", json={"motivo": "Dirección incompleta"})
    assert r.status_code == 200
    assert r.json()["estado_aprobacion"] == "RECHAZADO"


def test_rechazar_sin_motivo_400(monkeypatch):
    panel = _panel_pendiente()
    db = _db_con_panel_y_rm(panel, rm_gerente_id=3)

    def _raise(db_, panel_id, motivo, usuario_id=None):
        raise ValueError("Debe indicar el motivo del rechazo.")
    monkeypatch.setattr(mod.aprobacion_svc, "rechazar", _raise)

    client = _client(U(Rol.GERENTE_DISTRITO, gerente_id=3), db=db)
    r = client.post("/api/v1/farmacias/aprobacion/1/rechazar", json={})
    assert r.status_code == 400
    assert "motivo" in r.json()["detail"].lower()


# ─────────────────────────────────────────────────────────────────────────
# Auto-scope: un VM no ve el panel de otro
# ─────────────────────────────────────────────────────────────────────────

def test_scope_vm_ignora_vm_id_ajeno():
    """`_scope_vm` es el mecanismo de auto-scope de /panel: un REPRESENTANTE_MEDICO
    SIEMPRE se resuelve a su propio rm_id, sin importar qué vm_id pida."""
    user = U(Rol.REPRESENTANTE_MEDICO, rm_id=7)
    assert mod._scope_vm(user, vm_id=999) == 7
    assert mod._scope_vm(user, vm_id=None) == 7


def test_panel_listar_vm_consulta_su_propio_rm_id_no_el_ajeno():
    db = MagicMock()
    # panel_listar encadena DOS .filter() (vm_id + activo, incluir_inactivos=False por defecto)
    # antes de .order_by().all() — hay que vaciar el chain completo para que el código tome el
    # camino "if not paneles: return []" y no siga hasta la query de Farmacia (que pisaría el
    # .filter.call_args que queremos inspeccionar).
    db.query.return_value.filter.return_value.filter.return_value.order_by.return_value.all.return_value = []

    client = _client(U(Rol.REPRESENTANTE_MEDICO, rm_id=7), db=db)
    r = client.get("/api/v1/farmacias/panel", params={"vm_id": 999})
    assert r.status_code == 200
    assert r.json() == []

    # La condición armada por el auto-scope debe filtrar por el rm_id PROPIO (7), no 999
    filtro = db.query.return_value.filter.call_args[0][0]
    assert filtro.right.value == 7


def test_gd_no_ve_panel_de_vm_ajeno_403():
    db = MagicMock()
    rm_de_otro_gerente = SimpleNamespace(id=999, gerente_id=42)
    db.query.return_value.filter.return_value.first.return_value = rm_de_otro_gerente

    client = _client(U(Rol.GERENTE_DISTRITO, gerente_id=3), db=db)
    r = client.get("/api/v1/farmacias/panel", params={"vm_id": 999})
    assert r.status_code == 403


# ─────────────────────────────────────────────────────────────────────────
# F26: GET /farmacias/panel expone `motivo` de rechazo (Sub-parte A, Tarea 9)
# ─────────────────────────────────────────────────────────────────────────

def _db_panel(panel, maestro):
    """Doble de Session dispatchado por modelo (mismo patrón que `_db_con_panel_y_rm`
    arriba): así el guard RBAC (`require`, que hace su propio `db.query(func.max(...))`/
    `db.query(RolPermiso)` antes de entrar al endpoint) no desalinea un side_effect
    posicional — solo respondemos a los modelos que el endpoint realmente consulta."""
    db = MagicMock()

    def _query(modelo):
        q = MagicMock()
        nombre = getattr(modelo, "__name__", None)
        if nombre == "FarmaciaVisita":
            q.filter.return_value.filter.return_value.order_by.return_value.all.return_value = [panel]
        elif nombre == "Farmacia":
            q.filter.return_value.all.return_value = [maestro]
        return q
    db.query.side_effect = _query
    return db


def test_panel_listar_incluye_motivo_del_panel_cuando_rechazado():
    panel = SimpleNamespace(id=1, maestro_farmacia_id=50, vm_id=7, activo=True,
                            estado_aprobacion="RECHAZADO", ciclos_sin_visita=0,
                            motivo="Dirección incompleta")
    maestro = SimpleNamespace(id=50, nombre_completo="GBC PANTOJA", direccion="Calle 1",
                              encargado="Ana", estado="RECHAZADA", motivo_rechazo=None)
    db = _db_panel(panel, maestro)

    client = _client(U(Rol.REPRESENTANTE_MEDICO, rm_id=7), db=db)
    r = client.get("/api/v1/farmacias/panel")
    assert r.status_code == 200
    assert r.json()[0]["motivo"] == "Dirección incompleta"


def test_panel_listar_motivo_cae_al_del_maestro_si_panel_no_lo_trae():
    panel = SimpleNamespace(id=1, maestro_farmacia_id=50, vm_id=7, activo=True,
                            estado_aprobacion="RECHAZADO", ciclos_sin_visita=0,
                            motivo=None)
    maestro = SimpleNamespace(id=50, nombre_completo="GBC PANTOJA", direccion="Calle 1",
                              encargado="Ana", estado="RECHAZADA",
                              motivo_rechazo="Rechazado desde el maestro")
    db = _db_panel(panel, maestro)

    client = _client(U(Rol.REPRESENTANTE_MEDICO, rm_id=7), db=db)
    r = client.get("/api/v1/farmacias/panel")
    assert r.status_code == 200
    assert r.json()[0]["motivo"] == "Rechazado desde el maestro"


def test_panel_listar_motivo_nulo_si_no_esta_rechazado():
    panel = SimpleNamespace(id=1, maestro_farmacia_id=50, vm_id=7, activo=True,
                            estado_aprobacion="APROBADO", ciclos_sin_visita=0,
                            motivo=None)
    maestro = SimpleNamespace(id=50, nombre_completo="GBC PANTOJA", direccion="Calle 1",
                              encargado="Ana", estado="ACTIVA", motivo_rechazo=None)
    db = _db_panel(panel, maestro)

    client = _client(U(Rol.REPRESENTANTE_MEDICO, rm_id=7), db=db)
    r = client.get("/api/v1/farmacias/panel")
    assert r.status_code == 200
    assert r.json()[0]["motivo"] is None


# ─────────────────────────────────────────────────────────────────────────
# §3.2: GET /farmacias/aprobacion/pendientes reenvía `posible_duplicado` (Sub-parte A)
# ─────────────────────────────────────────────────────────────────────────

def test_aprobacion_pendientes_reenvia_posible_duplicado(monkeypatch):
    pendiente = {
        "id": 1, "maestro_farmacia_id": 50, "nombre_completo": "GBC PANTOJA",
        "direccion": "Calle 1", "encargado": "Ana", "estado_maestro": "PENDIENTE_APROBACION",
        "tipo_solicitud": "NUEVA", "vm_id": 7, "vm_nombre": "VM Siete",
        "fecha_solicitud": None,
        "posible_duplicado": [{"id": 77, "nombre_completo": "GBC PANTOJA 2"}],
    }
    monkeypatch.setattr(mod.aprobacion_svc, "pendientes_del_gd", lambda db_, gerente_id: [pendiente])

    client = _client(U(Rol.GERENTE_DISTRITO, gerente_id=3), db=MagicMock())
    r = client.get("/api/v1/farmacias/aprobacion/pendientes")
    assert r.status_code == 200
    assert r.json()[0]["posible_duplicado"] == [{"id": 77, "nombre_completo": "GBC PANTOJA 2"}]
