"""Tests del congelamiento de la planeación (jul-2026).

La planeación es el DENOMINADOR de la cobertura (`visitados / planeados`). Si un VM pudiera
editarla a mitad de ciclo, subiría su cobertura quitando del plan a los médicos que no visitó
— sin visitar a nadie más. Regla: borrador editable → Publicar la congela → solo un ADMIN la
desbloquea, con motivo, dejando rastro.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services import visita_planeacion_service as svc


def _db(ultimo_evento=None, filas_plan=1):
    """Sesión falsa: `_ultimo_evento` devuelve `ultimo_evento`; el count() de la planeación
    devuelve `filas_plan`."""
    db = MagicMock()
    cadena = db.query.return_value.filter.return_value
    cadena.order_by.return_value.first.return_value = ultimo_evento
    cadena.count.return_value = filas_plan
    return db


PUBLICADA = SimpleNamespace(evento="PUBLICADA", fecha=None, usuario_id=1, motivo=None, items=16)
DESBLOQUEADA = SimpleNamespace(evento="DESBLOQUEADA", fecha=None, usuario_id=1, motivo="error", items=None)


# ── esta_publicada: el estado sale del ULTIMO evento ──────────────────────────

def test_sin_eventos_es_borrador():
    assert svc.esta_publicada(_db(None), 47, 41) is False


def test_con_evento_publicada_esta_congelada():
    assert svc.esta_publicada(_db(PUBLICADA), 47, 41) is True


def test_tras_desbloquear_vuelve_a_borrador():
    """El log es append-only: el evento PUBLICADA sigue ahí, pero manda el último."""
    assert svc.esta_publicada(_db(DESBLOQUEADA), 47, 41) is False


# ── El guardado ──────────────────────────────────────────────────────────────

def test_guardar_una_planeacion_publicada_se_rechaza(monkeypatch):
    """EL PUNTO DE TODO: sin este guard, el delete-then-insert reescribiría el plan
    congelado y movería el denominador de la cobertura."""
    monkeypatch.setattr(svc, "_guard_ciclo_abierto", lambda db, c: None)
    with pytest.raises(svc.PlaneacionPublicadaError):
        svc.guardar_planeacion(_db(PUBLICADA), 47, 41, [], usuario_id=1)


def test_el_error_dice_que_hacer_no_solo_que_no_se_puede(monkeypatch):
    monkeypatch.setattr(svc, "_guard_ciclo_abierto", lambda db, c: None)
    with pytest.raises(svc.PlaneacionPublicadaError) as e:
        svc.guardar_planeacion(_db(PUBLICADA), 47, 41, [], usuario_id=1)
    assert "administrador" in str(e.value) and "desbloquear" in str(e.value)


# ── Publicar ─────────────────────────────────────────────────────────────────

def test_publicar_dos_veces_se_rechaza(monkeypatch):
    monkeypatch.setattr(svc, "_guard_ciclo_abierto", lambda db, c: None)
    with pytest.raises(svc.PlaneacionPublicadaError):
        svc.publicar_planeacion(_db(PUBLICADA), 47, 41, usuario_id=1)


def test_publicar_sin_planeacion_se_rechaza(monkeypatch):
    """Publicar un plan vacío dejaría la cobertura sin denominador."""
    monkeypatch.setattr(svc, "_guard_ciclo_abierto", lambda db, c: None)
    with pytest.raises(ValueError, match="No hay planeación que publicar"):
        svc.publicar_planeacion(_db(None, filas_plan=0), 47, 41, usuario_id=1)


def test_publicar_un_borrador_con_datos_funciona(monkeypatch):
    monkeypatch.setattr(svc, "_guard_ciclo_abierto", lambda db, c: None)
    r = svc.publicar_planeacion(_db(None, filas_plan=16), 47, 41, usuario_id=1)
    assert r == {"publicada": True, "items": 16, "ciclo_id": 41}


# ── Desbloquear (solo ADMIN — el rol lo exige el router) ──────────────────────

def test_desbloquear_sin_motivo_se_rechaza(monkeypatch):
    """Sin motivo, desbloquear sería una vía silenciosa para maquillar la cobertura."""
    monkeypatch.setattr(svc, "_guard_ciclo_abierto", lambda db, c: None)
    with pytest.raises(ValueError, match="motivo"):
        svc.desbloquear_planeacion(_db(PUBLICADA), 47, 41, usuario_id=1, motivo="   ")


def test_desbloquear_algo_no_publicado_se_rechaza(monkeypatch):
    monkeypatch.setattr(svc, "_guard_ciclo_abierto", lambda db, c: None)
    with pytest.raises(ValueError, match="no está publicada"):
        svc.desbloquear_planeacion(_db(None), 47, 41, usuario_id=1, motivo="error de captura")


def test_desbloquear_publicada_con_motivo_funciona(monkeypatch):
    monkeypatch.setattr(svc, "_guard_ciclo_abierto", lambda db, c: None)
    r = svc.desbloquear_planeacion(_db(PUBLICADA), 47, 41, usuario_id=1, motivo="error de captura")
    assert r == {"publicada": False, "ciclo_id": 41}


# ── El error debe llegar al usuario como 409, no como 500 ─────────────────────

def test_planeacion_publicada_no_es_valueerror():
    """REGRESIÓN: `PlaneacionPublicadaError` hereda de Exception, no de ValueError. El router
    solo atrapaba ValueError, así que escapaba como 500 'Error interno del servidor' y el
    representante nunca leía el motivo real. El except propio del router es obligatorio."""
    assert not issubclass(svc.PlaneacionPublicadaError, ValueError)


def test_el_router_traduce_la_excepcion_a_409():
    """Fija el contrato: si alguien quita el except, este test cae."""
    import inspect
    from app.api.v1.routers import visita
    fuente = inspect.getsource(visita.guardar_planeacion)
    assert "PlaneacionPublicadaError" in fuente
    assert "409" in fuente or "HTTP_409_CONFLICT" in fuente
