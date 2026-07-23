"""Tests Farmacias — Tarea 4 (flujo de aprobación VM→GD, acciones A/B, bandeja).

Convención del proyecto (ver test_maestro_farmacia_service.py / test_visita_service.py):
dobles de Session (`MagicMock` + `side_effect` por llamada a `db.query(...)`, o
`SimpleNamespace` para los objetos ORM) en vez de una BD real.
"""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services import farmacia_aprobacion_service as svc


def _fake_db():
    db = MagicMock()
    db.refresh.side_effect = lambda obj: None
    return db


def _panel(**over):
    base = dict(id=1, vm_id=7, maestro_farmacia_id=50, estado_aprobacion="PENDIENTE_ALTA",
                ciclo_alta_id=None, aprobado_por=None, fecha_aprobacion=None,
                motivo=None, activo=True)
    base.update(over)
    return SimpleNamespace(**base)


def _maestro(**over):
    base = dict(id=50, pais_codigo="DO", estado="PENDIENTE_APROBACION", origen="VM",
                nombre_completo="GBC PANTOJA", direccion="Calle 1", encargado="Ana",
                aprobado_por=None, fecha_aprobacion=None, motivo_rechazo=None,
                updated_at=None)
    base.update(over)
    return SimpleNamespace(**base)


class _Q:
    """Doble simple de Session.query(...).filter(...).first()/.all()/.order_by()."""
    def __init__(self, rows=None, first=None):
        self._rows = rows if rows is not None else []
        self._first = first

    def filter(self, *a, **k):
        return self

    def order_by(self, *a, **k):
        return self

    def all(self):
        return self._rows

    def first(self):
        return self._first


# ── Acción A: agregar farmacia existente (ACTIVA) al panel ─────────────────────
def test_agregar_al_panel_crea_pendiente_alta(monkeypatch):
    db = _fake_db()
    db.query.return_value.filter.return_value.first.return_value = _maestro(estado="ACTIVA")
    monkeypatch.setattr(svc, "_pais_de_vm", lambda db_, vm: "DO")
    monkeypatch.setattr(svc, "_panel_existente", lambda *a, **k: None)
    panel = svc.solicitar_agregar_al_panel(db, vm_id=7, maestro_farmacia_id=50, usuario_id=3)
    assert panel.estado_aprobacion == "PENDIENTE_ALTA"
    assert panel.vm_id == 7 and panel.maestro_farmacia_id == 50
    assert panel.solicitado_por == 3
    db.add.assert_called_once()
    db.commit.assert_called_once()


def test_agregar_al_panel_rechaza_si_ya_esta_en_el_panel(monkeypatch):
    db = _fake_db()
    db.query.return_value.filter.return_value.first.return_value = _maestro(estado="ACTIVA")
    monkeypatch.setattr(svc, "_pais_de_vm", lambda db_, vm: "DO")
    monkeypatch.setattr(svc, "_panel_existente", lambda *a, **k: _panel())
    with pytest.raises(ValueError, match="ya está en tu panel"):
        svc.solicitar_agregar_al_panel(db, vm_id=7, maestro_farmacia_id=50, usuario_id=3)
    db.add.assert_not_called()


# ── Acción A: validación del maestro (hallazgo importante 3) ───────────────────
def test_agregar_al_panel_falla_si_maestro_no_existe(monkeypatch):
    db = _fake_db()
    monkeypatch.setattr(svc, "_pais_de_vm", lambda db_, vm: "DO")
    db.query.return_value.filter.return_value.first.return_value = None
    with pytest.raises(ValueError, match="no existe en el maestro"):
        svc.solicitar_agregar_al_panel(db, vm_id=7, maestro_farmacia_id=999, usuario_id=3)
    db.add.assert_not_called()


# ── Acción A: validación del VM (hallazgo menor 4) ──────────────────────────────
def test_agregar_al_panel_falla_si_vm_no_existe(monkeypatch):
    """Hallazgo menor 4: simetría con `solicitar_crear` — un `vm_id` que no resuelve
    a un RM debía seguir de largo y reventar en 500 más adelante al insertar el panel
    (FK). Ahora es un ValueError claro, sin ni siquiera consultar el maestro."""
    db = _fake_db()
    monkeypatch.setattr(svc, "_pais_de_vm", lambda db_, vm: None)
    with pytest.raises(ValueError, match="no existe"):
        svc.solicitar_agregar_al_panel(db, vm_id=99999, maestro_farmacia_id=50, usuario_id=3)
    db.query.assert_not_called()
    db.add.assert_not_called()


@pytest.mark.parametrize("estado", ["PENDIENTE_APROBACION", "RECHAZADA", "INACTIVA"])
def test_agregar_al_panel_falla_si_maestro_no_esta_activa(estado):
    db = _fake_db()
    db.query.return_value.filter.return_value.first.return_value = _maestro(estado=estado)
    with pytest.raises(ValueError, match="no está activa"):
        svc.solicitar_agregar_al_panel(db, vm_id=7, maestro_farmacia_id=50, usuario_id=3)
    db.add.assert_not_called()


def test_agregar_al_panel_falla_si_es_de_otro_pais(monkeypatch):
    db = _fake_db()
    db.query.return_value.filter.return_value.first.return_value = _maestro(
        estado="ACTIVA", pais_codigo="GT")
    monkeypatch.setattr(svc, "_pais_de_vm", lambda db_, vm: "DO")
    with pytest.raises(ValueError, match="país"):
        svc.solicitar_agregar_al_panel(db, vm_id=7, maestro_farmacia_id=50, usuario_id=3)
    db.add.assert_not_called()


# ── Acción B: crear farmacia nueva + panel enlazado ─────────────────────────────
def test_solicitar_crear_crea_maestro_pendiente_y_panel_pendiente(monkeypatch):
    from app.services import maestro_farmacia_service as mm

    db = _fake_db()
    monkeypatch.setattr(svc, "_pais_de_vm", lambda db_, vm: "DO")
    maestro_creado = _maestro(id=99, estado="PENDIENTE_APROBACION", origen="VM")
    llamado = {}

    def _crear_maestro(db_, pais, datos, *, origen, estado, usuario_id=None):
        llamado.update(pais=pais, origen=origen, estado=estado, datos=datos)
        return maestro_creado
    monkeypatch.setattr(mm, "crear_maestro", _crear_maestro)
    monkeypatch.setattr(svc.maestro_svc, "crear_maestro", _crear_maestro)

    datos = {"direccion": "Calle 1", "encargado": "Ana", "cadena": "GBC", "sucursal": "Pantoja",
             "es_cadena": True}
    panel = svc.solicitar_crear(db, vm_id=7, datos=datos, usuario_id=3)

    assert llamado["pais"] == "DO"
    assert llamado["origen"] == "VM"
    assert llamado["estado"] == "PENDIENTE_APROBACION"
    assert panel.maestro_farmacia_id == 99
    assert panel.estado_aprobacion == "PENDIENTE_ALTA"
    assert panel.solicitado_por == 3
    db.add.assert_called_once()
    db.commit.assert_called_once()


def test_solicitar_crear_propaga_duplicado_duro(monkeypatch):
    from app.services import maestro_farmacia_service as mm

    db = _fake_db()
    monkeypatch.setattr(svc, "_pais_de_vm", lambda db_, vm: "DO")

    def _duro(*a, **k):
        raise mm.DuplicadoDuroError([{"id": 5, "nombre_completo": "GBC PANTOJA"}])
    monkeypatch.setattr(svc.maestro_svc, "crear_maestro", _duro)

    with pytest.raises(mm.DuplicadoDuroError):
        svc.solicitar_crear(db, vm_id=7, datos={"direccion": "x", "encargado": "y"}, usuario_id=3)
    db.add.assert_not_called()


def test_solicitar_crear_falla_si_vm_no_existe(monkeypatch):
    """Hallazgo menor 4: `vm_id` que no resuelve a un RM debía reventar en 500 al
    intentar `Farmacia(pais_codigo=None, ...)` (columna NOT NULL) — ahora es un
    ValueError claro, sin tocar el maestro."""
    db = _fake_db()
    monkeypatch.setattr(svc, "_pais_de_vm", lambda db_, vm: None)

    def _no_deberia_llamarse(*a, **k):
        raise AssertionError("crear_maestro no debe llamarse si el VM no existe")
    monkeypatch.setattr(svc.maestro_svc, "crear_maestro", _no_deberia_llamarse)

    with pytest.raises(ValueError, match="no existe"):
        svc.solicitar_crear(db, vm_id=99999, datos={"direccion": "x", "encargado": "y"}, usuario_id=3)
    db.add.assert_not_called()


def test_solicitar_crear_propaga_bloqueante(monkeypatch):
    db = _fake_db()
    monkeypatch.setattr(svc, "_pais_de_vm", lambda db_, vm: "DO")

    def _sin_direccion(*a, **k):
        raise ValueError("Debe completar la dirección de la farmacia para poder grabarla.")
    monkeypatch.setattr(svc.maestro_svc, "crear_maestro", _sin_direccion)

    with pytest.raises(ValueError, match="dirección"):
        svc.solicitar_crear(db, vm_id=7, datos={"direccion": "  ", "encargado": "Ana"}, usuario_id=3)


# ── aprobar ──────────────────────────────────────────────────────────────────
def test_aprobar_activa_maestro_y_sella_panel(monkeypatch):
    db = _fake_db()
    panel = _panel()
    maestro = _maestro()
    db.query.side_effect = [_Q(first=panel), _Q(first=maestro)]
    monkeypatch.setattr(svc, "ciclo_actual_id", lambda db_, vm_id: 42)

    resultado = svc.aprobar(db, panel_id=1, usuario_id=9)

    assert resultado.estado_aprobacion == "APROBADO"
    assert resultado.ciclo_alta_id == 42
    assert resultado.aprobado_por == 9
    assert resultado.fecha_aprobacion is not None
    assert maestro.estado == "ACTIVA"
    assert maestro.aprobado_por == 9
    db.commit.assert_called_once()


def test_aprobar_no_reactiva_maestro_ya_activo(monkeypatch):
    """Acción A: el maestro ya estaba ACTIVA (por eso se pudo agregar); aprobar el panel
    no debe pisar aprobado_por/fecha_aprobacion del alta original del maestro."""
    db = _fake_db()
    panel = _panel()
    maestro = _maestro(estado="ACTIVA", aprobado_por=1, fecha_aprobacion="ya-fijado")
    db.query.side_effect = [_Q(first=panel), _Q(first=maestro)]
    monkeypatch.setattr(svc, "ciclo_actual_id", lambda db_, vm_id: 42)

    svc.aprobar(db, panel_id=1, usuario_id=9)

    assert maestro.estado == "ACTIVA"
    assert maestro.aprobado_por == 1
    assert maestro.fecha_aprobacion == "ya-fijado"


# ── aprobar: guard de maestro desactivado (hallazgo menor M3) ──────────────────
@pytest.mark.parametrize("estado", ["INACTIVA", "RECHAZADA"])
def test_aprobar_falla_si_maestro_no_esta_activo_ni_pendiente(estado):
    """Si el maestro quedó INACTIVA/RECHAZADA entre la Acción A y la aprobación (p.ej.
    un ADMIN lo desactivó), aprobar el panel NO debe resucitarlo en silencio."""
    db = _fake_db()
    panel = _panel()
    maestro = _maestro(estado=estado)
    db.query.side_effect = [_Q(first=panel), _Q(first=maestro)]

    with pytest.raises(ValueError, match="no está activa"):
        svc.aprobar(db, panel_id=1, usuario_id=9)

    assert panel.estado_aprobacion == "PENDIENTE_ALTA"
    assert maestro.estado == estado
    db.commit.assert_not_called()


def test_aprobar_falla_si_panel_no_existe():
    db = _fake_db()
    db.query.side_effect = [_Q(first=None)]
    with pytest.raises(ValueError, match="no existe"):
        svc.aprobar(db, panel_id=999, usuario_id=9)


def test_aprobar_falla_si_no_esta_pendiente():
    db = _fake_db()
    db.query.side_effect = [_Q(first=_panel(estado_aprobacion="APROBADO"))]
    with pytest.raises(ValueError, match="pendiente"):
        svc.aprobar(db, panel_id=1, usuario_id=9)


# ── rechazar ─────────────────────────────────────────────────────────────────
def test_rechazar_sin_motivo_falla():
    db = _fake_db()
    with pytest.raises(ValueError, match="motivo"):
        svc.rechazar(db, panel_id=1, motivo=None, usuario_id=9)
    with pytest.raises(ValueError, match="motivo"):
        svc.rechazar(db, panel_id=1, motivo="   ", usuario_id=9)
    db.query.assert_not_called()


def test_rechazar_con_motivo_marca_rechazada_y_guarda_motivo():
    db = _fake_db()
    panel = _panel()
    maestro = _maestro(estado="PENDIENTE_APROBACION", origen="VM")
    db.query.side_effect = [_Q(first=panel), _Q(first=maestro)]

    resultado = svc.rechazar(db, panel_id=1, motivo="Dirección incompleta", usuario_id=9)

    assert resultado.estado_aprobacion == "RECHAZADO"
    assert resultado.motivo == "Dirección incompleta"
    assert resultado.activo is False
    assert maestro.estado == "RECHAZADA"
    assert maestro.motivo_rechazo == "Dirección incompleta"
    db.commit.assert_called_once()


def test_rechazar_no_toca_maestro_si_es_accion_a(monkeypatch):
    """Acción A (agregar existente): el maestro ya estaba ACTIVA de antes; rechazar el
    panel no debe convertir una farmacia activa en RECHAZADA."""
    db = _fake_db()
    panel = _panel()
    maestro = _maestro(estado="ACTIVA", origen="CONFIG")
    db.query.side_effect = [_Q(first=panel), _Q(first=maestro)]

    svc.rechazar(db, panel_id=1, motivo="No corresponde a mi zona", usuario_id=9)

    assert maestro.estado == "ACTIVA"
    assert maestro.motivo_rechazo is None


def test_rechazar_falla_si_no_esta_pendiente():
    db = _fake_db()
    db.query.side_effect = [_Q(first=_panel(estado_aprobacion="RECHAZADO"))]
    with pytest.raises(ValueError, match="pendiente"):
        svc.rechazar(db, panel_id=1, motivo="algo", usuario_id=9)


# ── editar_y_aprobar ─────────────────────────────────────────────────────────
def test_editar_y_aprobar_aplica_cambios_y_luego_aprueba(monkeypatch):
    db = _fake_db()
    panel = _panel()
    maestro = _maestro()

    # 1ra: _guard busca el panel. 2da: busca el maestro para editar.
    # 3ra/4ta: dentro de aprobar() se vuelve a buscar panel y maestro.
    db.query.side_effect = [_Q(first=panel), _Q(first=maestro), _Q(first=panel), _Q(first=maestro)]

    llamado = {}
    def _actualizar(db_, farmacia, cambios, usuario_id=None):
        llamado.update(cambios=cambios)
        farmacia.direccion = cambios.get("direccion", farmacia.direccion)
        return farmacia
    monkeypatch.setattr(svc.maestro_svc, "actualizar_maestro", _actualizar)
    monkeypatch.setattr(svc, "ciclo_actual_id", lambda db_, vm_id: 42)

    resultado = svc.editar_y_aprobar(db, panel_id=1, cambios={"direccion": "Calle nueva"}, usuario_id=9)

    assert llamado["cambios"] == {"direccion": "Calle nueva"}
    assert maestro.direccion == "Calle nueva"
    assert resultado.estado_aprobacion == "APROBADO"
    assert maestro.estado == "ACTIVA"


# ── pendientes_del_gd ────────────────────────────────────────────────────────
def test_pendientes_del_gd_filtra_por_distrito(monkeypatch):
    db = _fake_db()
    rm7 = SimpleNamespace(id=7, gerente_id=100, nombre="VM Siete")
    rm8 = SimpleNamespace(id=8, gerente_id=100, nombre="VM Ocho")
    panel_de_mi_equipo = _panel(id=1, vm_id=7, maestro_farmacia_id=50,
                                fecha_solicitud=datetime.now(timezone.utc))
    maestro = _maestro(id=50, estado="PENDIENTE_APROBACION", origen="VM")
    monkeypatch.setattr(svc.maestro_svc, "detectar_posibles_duplicados", lambda *a, **k: [])

    # Orden de queries dentro de pendientes_del_gd:
    # 1) RM del gerente -> [rm7, rm8]
    # 2) paneles PENDIENTE_ALTA de esos vm_ids -> [panel_de_mi_equipo]
    # 3) maestros de esos ids -> [maestro]
    # 4) RM de esos vm_ids (para nombre) -> [rm7]
    db.query.side_effect = [
        _Q(rows=[rm7, rm8]),
        _Q(rows=[panel_de_mi_equipo]),
        _Q(rows=[maestro]),
        _Q(rows=[rm7]),
    ]

    resultado = svc.pendientes_del_gd(db, gerente_id=100)

    assert len(resultado) == 1
    assert resultado[0]["id"] == 1
    assert resultado[0]["vm_nombre"] == "VM Siete"
    assert resultado[0]["tipo_solicitud"] == "NUEVA"
    assert resultado[0]["nombre_completo"] == "GBC PANTOJA"
    assert resultado[0]["posible_duplicado"] == []


def test_pendientes_del_gd_expone_posible_duplicado_para_alta_nueva(monkeypatch):
    """§3.2: alerta de posible duplicado VISIBLE en la bandeja (informativa, no bloquea)."""
    db = _fake_db()
    rm7 = SimpleNamespace(id=7, gerente_id=100, nombre="VM Siete")
    panel = _panel(id=1, vm_id=7, maestro_farmacia_id=50,
                  fecha_solicitud=datetime.now(timezone.utc))
    maestro = _maestro(id=50, estado="PENDIENTE_APROBACION", origen="VM",
                       nombre_completo="GBC PANTOJA")
    coincidencia = {"id": 77, "nombre_completo": "GBC PANTOJA 2"}
    llamada = {}

    def _fake_posibles(db_, pais, *, nombre_completo, excluir_id=None):
        llamada.update(pais=pais, nombre_completo=nombre_completo, excluir_id=excluir_id)
        return [coincidencia]
    monkeypatch.setattr(svc.maestro_svc, "detectar_posibles_duplicados", _fake_posibles)

    db.query.side_effect = [
        _Q(rows=[rm7]),
        _Q(rows=[panel]),
        _Q(rows=[maestro]),
        _Q(rows=[rm7]),
    ]

    resultado = svc.pendientes_del_gd(db, gerente_id=100)

    assert resultado[0]["posible_duplicado"] == [coincidencia]
    assert llamada == {"pais": "DO", "nombre_completo": "GBC PANTOJA", "excluir_id": 50}


def test_pendientes_del_gd_no_evalua_posible_duplicado_en_accion_a(monkeypatch):
    """Acción A (AGREGAR, maestro ya ACTIVA): no tiene sentido comparar la farmacia
    contra sí misma -> posible_duplicado vacío, sin ni siquiera llamar al detector."""
    db = _fake_db()
    rm7 = SimpleNamespace(id=7, gerente_id=100, nombre="VM Siete")
    panel = _panel(id=2, vm_id=7, maestro_farmacia_id=51,
                  fecha_solicitud=datetime.now(timezone.utc))
    maestro_activo = _maestro(id=51, estado="ACTIVA", origen="CONFIG")

    def _no_deberia_llamarse(*a, **k):
        raise AssertionError("detectar_posibles_duplicados no debe llamarse en Acción A")
    monkeypatch.setattr(svc.maestro_svc, "detectar_posibles_duplicados", _no_deberia_llamarse)

    db.query.side_effect = [
        _Q(rows=[rm7]),
        _Q(rows=[panel]),
        _Q(rows=[maestro_activo]),
        _Q(rows=[rm7]),
    ]

    resultado = svc.pendientes_del_gd(db, gerente_id=100)
    assert resultado[0]["posible_duplicado"] == []


def test_pendientes_del_gd_sin_equipo_devuelve_vacio():
    db = _fake_db()
    db.query.side_effect = [_Q(rows=[])]
    assert svc.pendientes_del_gd(db, gerente_id=999) == []


def test_pendientes_del_gd_marca_agregar_si_maestro_ya_estaba_activo():
    """Acción A: el maestro ya era ACTIVA antes del panel -> tipo_solicitud AGREGAR."""
    db = _fake_db()
    rm7 = SimpleNamespace(id=7, gerente_id=100, nombre="VM Siete")
    panel = _panel(id=2, vm_id=7, maestro_farmacia_id=51,
                   fecha_solicitud=datetime.now(timezone.utc))
    maestro_activo = _maestro(id=51, estado="ACTIVA", origen="CONFIG")

    db.query.side_effect = [
        _Q(rows=[rm7]),
        _Q(rows=[panel]),
        _Q(rows=[maestro_activo]),
        _Q(rows=[rm7]),
    ]

    resultado = svc.pendientes_del_gd(db, gerente_id=100)
    assert resultado[0]["tipo_solicitud"] == "AGREGAR"
