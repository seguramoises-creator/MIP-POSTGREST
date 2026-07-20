# -*- coding: utf-8 -*-
"""Activación de cuenta por enlace de un solo uso (jul-2026).

Sustituye el envío de contraseñas temporales por correo. Lo que se fija aquí:
el token no se guarda en claro, caduca, es de un solo uso, y una contraseña
débil NO lo consume (si no, el usuario se quedaría fuera por un error de tipeo).
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.services import activacion_service as svc


# ── Hash del token ───────────────────────────────────────────────────────────

def test_el_hash_es_determinista_para_poder_buscar_por_indice():
    """A diferencia de bcrypt, el mismo token da SIEMPRE el mismo hash: sin eso habría
    que recorrer la tabla entera comparando fila por fila."""
    assert svc._hash("abc123") == svc._hash("abc123")


def test_tokens_distintos_dan_hashes_distintos():
    assert svc._hash("abc123") != svc._hash("abc124")


def test_el_hash_mide_64_caracteres_hex():
    h = svc._hash("cualquier-cosa")
    assert len(h) == 64 and all(c in "0123456789abcdef" for c in h)


def test_el_token_se_normaliza_quitando_espacios():
    """Copiar el enlace del correo suele arrastrar espacios alrededor."""
    assert svc._hash("  tok  ") == svc._hash("tok")


# ── Enlace ───────────────────────────────────────────────────────────────────

def test_el_enlace_apunta_a_la_ruta_publica_de_activacion():
    url = svc._enlace("MI-TOKEN")
    assert url.endswith("/activar/MI-TOKEN")
    assert "//" in url          # conserva el esquema https://


def test_el_enlace_no_duplica_la_barra_final(monkeypatch):
    from app.core import config
    monkeypatch.setattr(config.settings, "PUBLIC_BASE_URL", "https://vista-mip.com/")
    assert svc._enlace("T") == "https://vista-mip.com/activar/T"


# ── Validación del token ─────────────────────────────────────────────────────

class _FakeQuery:
    def __init__(self, resultado): self._r = resultado
    def filter(self, *a, **k): return self
    def first(self): return self._r


class _FakeDB:
    """Devuelve `fila` para ActivacionCuenta y `usuario` para Usuario."""
    def __init__(self, fila=None, usuario=None): self.fila, self.usuario = fila, usuario
    def query(self, modelo):
        from app.models.usuario import ActivacionCuenta, Usuario
        return _FakeQuery(self.fila if modelo is ActivacionCuenta else self.usuario)


def _fila(**kw):
    base = dict(usuario_id=1, usado=False,
                expira_en=datetime.now(timezone.utc) + timedelta(hours=1))
    base.update(kw)
    return SimpleNamespace(**base)


_USUARIO_OK = SimpleNamespace(id=1, activo=True, username="ana", nombre_completo="Ana")


def test_token_vacio_se_rechaza():
    with pytest.raises(svc.TokenInvalidoError):
        svc.validar(_FakeDB(), "")


def test_token_inexistente_se_rechaza():
    with pytest.raises(svc.TokenInvalidoError):
        svc.validar(_FakeDB(fila=None), "no-existe")


def test_token_ya_usado_se_rechaza():
    """Un solo uso: aunque el enlace siga en el buzón, no vuelve a servir."""
    with pytest.raises(svc.TokenInvalidoError):
        svc.validar(_FakeDB(fila=_fila(usado=True), usuario=_USUARIO_OK), "tok")


def test_token_caducado_se_rechaza():
    vencido = _fila(expira_en=datetime.now(timezone.utc) - timedelta(minutes=1))
    with pytest.raises(svc.TokenInvalidoError):
        svc.validar(_FakeDB(fila=vencido, usuario=_USUARIO_OK), "tok")


def test_token_de_usuario_deshabilitado_se_rechaza():
    inactivo = SimpleNamespace(id=1, activo=False, username="ana", nombre_completo="Ana")
    with pytest.raises(svc.TokenInvalidoError):
        svc.validar(_FakeDB(fila=_fila(), usuario=inactivo), "tok")


def test_token_vigente_se_acepta():
    assert svc.validar(_FakeDB(fila=_fila(), usuario=_USUARIO_OK), "tok") is not None


def test_expira_en_naive_se_interpreta_como_utc():
    """Postgres devuelve la fecha sin zona; compararla con un datetime aware
    reventaría con TypeError si no se normalizara."""
    futuro_naive = (datetime.now(timezone.utc) + timedelta(hours=1)).replace(tzinfo=None)
    assert svc.validar(_FakeDB(fila=_fila(expira_en=futuro_naive), usuario=_USUARIO_OK), "t")


def test_todos_los_rechazos_dicen_lo_mismo():
    """Mensajes distintos revelarían si un token existió, si ya se usó o de quién era."""
    casos = [
        _FakeDB(fila=None),
        _FakeDB(fila=_fila(usado=True), usuario=_USUARIO_OK),
        _FakeDB(fila=_fila(expira_en=datetime.now(timezone.utc) - timedelta(minutes=1)),
                usuario=_USUARIO_OK),
    ]
    mensajes = set()
    for db in casos:
        try:
            svc.validar(db, "tok")
        except svc.TokenInvalidoError as e:
            mensajes.add(str(e))
    assert len(mensajes) == 1, f"los rechazos deben ser indistinguibles, hubo: {mensajes}"


# ── Caducidad configurable ───────────────────────────────────────────────────

def test_caduca_a_las_24_horas_por_defecto(monkeypatch):
    from app.services import config_service
    monkeypatch.setattr(config_service, "obtener", lambda db, clave: None)
    assert svc.expira_horas(None) == 24


def test_la_caducidad_es_configurable(monkeypatch):
    from app.services import config_service
    monkeypatch.setattr(config_service, "obtener",
                        lambda db, clave: "8" if clave == "ACTIVACION_EXPIRA_HORAS" else None)
    assert svc.expira_horas(None) == 8
