"""SCGCPR — Tests de política de contraseñas (complejidad por rol, expiración,
historial). Estilo mock-based del repo: `fake_db` (MagicMock) controla las
búsquedas de parámetros en Config.DIM_Parametro."""
import pytest

from app.services import password_policy_service as pp
from app.services import config_service
from app.models.usuario import Rol


def _sin_params(fake_db):
    """Toda búsqueda de parámetro devuelve None → se usan los defaults."""
    fake_db.query.return_value.filter.return_value.first.return_value = None
    return fake_db


def _param(fake_db, valor):
    """Toda búsqueda de parámetro devuelve un stub con `.valor`."""
    fake_db.query.return_value.filter.return_value.first.return_value = type("P", (), {"valor": valor})()
    return fake_db


# ── config_service.obtener_int ───────────────────────────────────────────────

def test_obtener_int_default(fake_db):
    _sin_params(fake_db)
    assert config_service.obtener_int(fake_db, "NO_EXISTE_X", 42) == 42


def test_obtener_int_valor(fake_db):
    _param(fake_db, "77")
    assert config_service.obtener_int(fake_db, "X", 42) == 77


def test_obtener_int_valor_invalido_usa_default(fake_db):
    _param(fake_db, "abc")
    assert config_service.obtener_int(fake_db, "X", 42) == 42


# ── complejidad ──────────────────────────────────────────────────────────────

def test_min_longitud_por_rol(fake_db):
    _sin_params(fake_db)
    assert pp.min_longitud(fake_db, Rol.ADMIN) == 12
    assert pp.min_longitud(fake_db, Rol.REPRESENTANTE_MEDICO) == 8


def test_complejidad_ok_no_admin(fake_db):
    _sin_params(fake_db)
    pp.validar_complejidad(fake_db, "Abcdef1!", Rol.REPRESENTANTE_MEDICO)  # 8 chars, no lanza


def test_complejidad_admin_requiere_12(fake_db):
    _sin_params(fake_db)
    with pytest.raises(ValueError, match="al menos 12"):
        pp.validar_complejidad(fake_db, "Abcdef1!", Rol.ADMIN)


@pytest.mark.parametrize("pwd,msg", [
    ("abcdef1!", "mayúscula"),
    ("ABCDEF1!", "minúscula"),
    ("Abcdefg!", "número"),
    ("Abcdefg1", "especial"),
    ("Ab1!",     "al menos 8"),
])
def test_complejidad_reglas(fake_db, pwd, msg):
    _sin_params(fake_db)
    with pytest.raises(ValueError, match=msg):
        pp.validar_complejidad(fake_db, pwd, Rol.REPRESENTANTE_MEDICO)


# ── historial y estado ───────────────────────────────────────────────────────
from datetime import datetime, timezone, timedelta  # noqa: E402
from app.core.security import hash_password  # noqa: E402


class _Q:
    """Query encadenada mínima que resuelve en `rows`."""
    def __init__(self, rows):
        self.rows = rows
    def filter(self, *a, **k):
        return self
    def order_by(self, *a, **k):
        return self
    def limit(self, *a, **k):
        return self
    def offset(self, *a, **k):
        return self
    def all(self):
        return self.rows


def _user(pwd="Abcdef1!", debe=False, actualizado=None):
    return type("U", (), {
        "id": 1,
        "hashed_password": hash_password(pwd),
        "debe_cambiar_password": debe,
        "password_actualizado_en": actualizado if actualizado is not None else datetime.now(timezone.utc),
    })()


def test_reutiliza_actual(monkeypatch, fake_db):
    monkeypatch.setattr(pp.config_service, "obtener_int", lambda db, k, d: 0)
    u = _user("Abcdef1!")
    assert pp.contrasena_reutilizada(fake_db, u, "Abcdef1!") is True   # = actual
    assert pp.contrasena_reutilizada(fake_db, u, "Zxcvbn9@") is False  # distinta, N=0


def test_reutiliza_historial(monkeypatch, fake_db):
    monkeypatch.setattr(pp.config_service, "obtener_int", lambda db, k, d: 5)
    fake_db.query.return_value = _Q([type("H", (), {"hashed_password": hash_password("Oldpass9!")})()])
    u = _user("Actual12!")
    assert pp.contrasena_reutilizada(fake_db, u, "Oldpass9!") is True   # coincide con historial


def test_registrar_poda(monkeypatch, fake_db):
    monkeypatch.setattr(pp.config_service, "obtener_int", lambda db, k, d: 3)
    s1, s2 = object(), object()
    fake_db.query.return_value = _Q([s1, s2])  # 2 sobrantes tras offset(3)
    pp.registrar_historial(fake_db, 1, hash_password("Nuevo123!"))
    assert fake_db.add.called
    assert fake_db.delete.call_count == 2


def _patch_estado(monkeypatch, activa=True, dias=90, aviso=7):
    monkeypatch.setattr(pp.config_service, "obtener_bool", lambda db, k, d: activa)
    monkeypatch.setattr(pp.config_service, "obtener_int",
                        lambda db, k, d: {"PASSWORD_EXPIRACION_DIAS": dias, "PASSWORD_AVISO_DIAS": aviso}.get(k, d))


def test_estado_primer_login(monkeypatch, fake_db):
    _patch_estado(monkeypatch)
    est = pp.estado_password(fake_db, _user(debe=True))
    assert est["debe_cambiar"] is True and est["motivo"] == "primer_login"


def test_estado_expirada(monkeypatch, fake_db):
    _patch_estado(monkeypatch)
    u = _user(actualizado=datetime.now(timezone.utc) - timedelta(days=100))
    est = pp.estado_password(fake_db, u)
    assert est["debe_cambiar"] is True and est["motivo"] == "expirada"


def test_estado_por_expirar(monkeypatch, fake_db):
    _patch_estado(monkeypatch)
    u = _user(actualizado=datetime.now(timezone.utc) - timedelta(days=85))
    est = pp.estado_password(fake_db, u)
    assert est["motivo"] == "por_expirar" and 0 <= est["dias_para_expirar"] <= 7


def test_estado_ok(monkeypatch, fake_db):
    _patch_estado(monkeypatch)
    u = _user(actualizado=datetime.now(timezone.utc) - timedelta(days=10))
    est = pp.estado_password(fake_db, u)
    assert est["debe_cambiar"] is False and est["motivo"] == "ok"


def test_estado_expiracion_desactivada(monkeypatch, fake_db):
    _patch_estado(monkeypatch, activa=False)
    u = _user(actualizado=datetime.now(timezone.utc) - timedelta(days=999))
    est = pp.estado_password(fake_db, u)
    assert est["debe_cambiar"] is False and est["dias_para_expirar"] is None
