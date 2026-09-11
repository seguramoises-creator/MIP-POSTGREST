"""Tests del circuito de aprobación de la planeación (sep-2026).

El representante arma su planeación y la ENVÍA; su Gerente de Distrito la APRUEBA (y con
eso queda publicada y congelada) o la DEVUELVE con motivo. Estados, por el último evento:

    (sin eventos) → BORRADOR ─enviar→ ENVIADA ─aprobar→ PUBLICADA
                                         └──devolver→ DEVUELTA ─enviar→ ENVIADA …
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services import visita_planeacion_service as svc


def _db(ultimo_evento=None, filas_plan=1):
    db = MagicMock()
    cadena = db.query.return_value.filter.return_value
    cadena.order_by.return_value.first.return_value = ultimo_evento
    cadena.count.return_value = filas_plan
    return db


def _ev(evento, motivo=None):
    return SimpleNamespace(evento=evento, fecha=None, usuario_id=1, motivo=motivo, items=10)


@pytest.fixture(autouse=True)
def _sin_guard_de_ciclo(monkeypatch):
    monkeypatch.setattr(svc, "_guard_ciclo_abierto", lambda db, c: None)
    monkeypatch.setattr(svc, "top_sin_planear", lambda db, v, c: [])
    monkeypatch.setattr(svc, "_avisar_gerente", lambda db, v, n: None)


def _eventos_escritos(db) -> list[str]:
    return [c.args[0].evento for c in db.add.call_args_list]


# ── Estados ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("ultimo, esperado", [
    (None, "BORRADOR"), (_ev("DESBLOQUEADA"), "BORRADOR"), (_ev("ENVIADA"), "ENVIADA"),
    (_ev("PUBLICADA"), "PUBLICADA"), (_ev("DEVUELTA", "falta el Dr. X"), "DEVUELTA"),
])
def test_el_estado_sale_del_ultimo_evento(ultimo, esperado):
    assert svc.estado_actual(_db(ultimo), 47, 41) == esperado


# ── Enviar ───────────────────────────────────────────────────────────────────

def test_enviar_un_borrador_lo_deja_enviado():
    db = _db(None, filas_plan=12)
    r = svc.enviar_planeacion(db, 47, 41, usuario_id=9)
    assert r == {"estado": "ENVIADA", "items": 12, "ciclo_id": 41}
    assert _eventos_escritos(db) == ["ENVIADA"]


def test_una_devuelta_se_puede_reenviar():
    db = _db(_ev("DEVUELTA", "revisa la semana 4"))
    assert svc.enviar_planeacion(db, 47, 41, usuario_id=9)["estado"] == "ENVIADA"


def test_enviar_vacia_se_rechaza():
    with pytest.raises(ValueError, match="No hay planeación que enviar"):
        svc.enviar_planeacion(_db(None, filas_plan=0), 47, 41, usuario_id=9)


def test_enviar_dos_veces_se_rechaza():
    with pytest.raises(svc.PlaneacionEnRevisionError):
        svc.enviar_planeacion(_db(_ev("ENVIADA")), 47, 41, usuario_id=9)


def test_enviar_sin_los_top_se_rechaza(monkeypatch):
    monkeypatch.setattr(svc, "top_sin_planear", lambda db, v, c: [{"id": 1, "nombre": "DR. TOP"}])
    with pytest.raises(svc.TopSinPlanearError, match="DR. TOP"):
        svc.enviar_planeacion(_db(None), 47, 41, usuario_id=9)


# ── Mientras está enviada, el representante no la toca ────────────────────────

def test_guardar_una_enviada_se_rechaza():
    """EL PUNTO: si pudiera seguir editándola, el gerente aprobaría otra cosa que la leída."""
    with pytest.raises(svc.PlaneacionEnRevisionError, match="revisión"):
        svc.guardar_planeacion(_db(_ev("ENVIADA")), 47, 41, [], usuario_id=9)


def test_la_revision_se_traduce_a_409_como_la_publicada():
    """Hereda de PlaneacionPublicadaError: el except del router que ya daba 409 la cubre."""
    assert issubclass(svc.PlaneacionEnRevisionError, svc.PlaneacionPublicadaError)


def test_guardar_una_devuelta_si_se_puede(monkeypatch):
    monkeypatch.setattr(svc, "_validar", lambda items, nombres=None: None)
    n = svc.guardar_planeacion(_db(_ev("DEVUELTA", "x")), 47, 41, [], usuario_id=9)
    assert n == 0


# ── Aprobar ──────────────────────────────────────────────────────────────────

def test_aprobar_una_enviada_la_publica():
    db = _db(_ev("ENVIADA"), filas_plan=12)
    r = svc.aprobar_planeacion(db, 47, 41, usuario_id=3)
    assert r["estado"] == "PUBLICADA" and r["publicada"] is True and r["items"] == 12
    # Aprobar ES publicar: mismo evento, así la cobertura y los guards no cambian.
    assert _eventos_escritos(db) == ["PUBLICADA"]


@pytest.mark.parametrize("ultimo", [None, _ev("PUBLICADA"), _ev("DEVUELTA", "x")])
def test_solo_se_aprueba_lo_enviado(ultimo):
    with pytest.raises(ValueError, match="no está pendiente de aprobación"):
        svc.aprobar_planeacion(_db(ultimo), 47, 41, usuario_id=3)


def test_aprobar_vuelve_a_exigir_los_top(monkeypatch):
    """Entre el envío y la aprobación pudo marcarse un TOP nuevo."""
    monkeypatch.setattr(svc, "top_sin_planear", lambda db, v, c: [{"id": 1, "nombre": "DR. NUEVO"}])
    with pytest.raises(svc.TopSinPlanearError):
        svc.aprobar_planeacion(_db(_ev("ENVIADA")), 47, 41, usuario_id=3)


# ── Devolver ─────────────────────────────────────────────────────────────────

def test_devolver_exige_motivo():
    with pytest.raises(ValueError, match="corregir"):
        svc.devolver_planeacion(_db(_ev("ENVIADA")), 47, 41, usuario_id=3, motivo="  ")


def test_devolver_una_enviada_guarda_el_motivo():
    db = _db(_ev("ENVIADA"))
    r = svc.devolver_planeacion(db, 47, 41, usuario_id=3, motivo="Falta la revisita del Dr. Pérez")
    assert r == {"estado": "DEVUELTA", "ciclo_id": 41}
    ev = db.add.call_args.args[0]
    assert ev.evento == "DEVUELTA" and ev.motivo == "Falta la revisita del Dr. Pérez"


def test_no_se_devuelve_lo_que_no_esta_enviado():
    with pytest.raises(ValueError, match="no está pendiente"):
        svc.devolver_planeacion(_db(None), 47, 41, usuario_id=3, motivo="x")


# ── Los errores de validación nombran al médico ───────────────────────────────

def test_el_error_de_validacion_nombra_al_medico():
    """Antes decía «(médico 6165)»: el representante no sabía a quién corregir."""
    from app.schemas.visita import PlaneacionItem
    items = [PlaneacionItem(medico_id=6165, tipo_visita="V", semana=2, dia_semana="Martes"),
             PlaneacionItem(medico_id=6165, tipo_visita="R", semana=2, dia_semana="Martes")]
    with pytest.raises(ValueError, match="ALBA NELLYS PÉREZ"):
        svc._validar(items, {6165: "ALBA NELLYS PÉREZ"})
    with pytest.raises(ValueError, match="médico 6165"):   # sin nombre conocido, el id
        svc._validar(items)


# ── El ciclo que se trabaja, dicho con nombre, fechas y semana ────────────────

def test_ciclo_info_da_nombre_fechas_y_semana(monkeypatch):
    import datetime as dt
    import app.core.tiempo as tiempo
    ciclo = SimpleNamespace(id=53, nombre="Ciclo 9 2026", cerrado=False, pais_codigo="DO",
                            fecha_inicio=dt.date(2026, 9, 1), fecha_fin=dt.date(2026, 9, 28))
    db = MagicMock()
    db.get.return_value = ciclo
    monkeypatch.setattr(tiempo, "hoy_local", lambda db, p: dt.date(2026, 9, 11))
    info = svc._ciclo_info(db, 53)
    assert info["nombre"] == "Ciclo 9 2026" and info["fecha_inicio"] == "2026-09-01"
    assert info["semana"] == 2
    # Fuera de sus fechas no se inventa una semana.
    monkeypatch.setattr(tiempo, "hoy_local", lambda db, p: dt.date(2026, 10, 5))
    assert svc._ciclo_info(db, 53)["semana"] is None


# ── El router ────────────────────────────────────────────────────────────────

def test_aprobar_y_devolver_exigen_que_sea_de_su_equipo():
    """Fija el contrato: sin `_exigir_equipo`, un GD aprobaría la de otro distrito."""
    import inspect
    from app.api.v1.routers import visita
    for fn in (visita.aprobar_planeacion, visita.devolver_planeacion, visita.detalle_planeacion):
        assert "_exigir_equipo" in inspect.getsource(fn), fn.__name__
