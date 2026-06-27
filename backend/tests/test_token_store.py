"""
Tests del token_store (blacklist de refresh tokens en BD).

Se prueban como unidades, con una `Session` mock (`fake_db`): se controla el
resultado terminal de `db.query(...).filter(...).first()` para cubrir las ramas
de negocio sin tocar una BD real. La verificación contra BD real se hizo aparte.
"""
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

from app.core.token_store import _jti_de, revocar_token, token_esta_revocado


def _exp_futuro() -> int:
    return int((datetime.now(timezone.utc) + timedelta(days=1)).timestamp())


# ── _jti_de ──────────────────────────────────────────────────────────────────

def test_jti_usa_claim_jti_si_existe():
    payload = {"sub": "5", "exp": 123, "jti": "abc123"}
    assert _jti_de(payload) == "abc123"


def test_jti_cae_a_sub_exp_si_no_hay_jti():
    payload = {"sub": "5", "exp": 123}
    assert _jti_de(payload) == "5:123"


# ── token_esta_revocado ──────────────────────────────────────────────────────

def _fake_db_con_first(resultado):
    """Session mock cuyo db.query(...).filter(...).first() devuelve `resultado`."""
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = resultado
    return db


def test_no_revocado_cuando_no_esta_en_tabla():
    db = _fake_db_con_first(None)
    assert token_esta_revocado(db, {"jti": "x", "exp": _exp_futuro()}) is False


def test_revocado_cuando_existe_fila():
    db = _fake_db_con_first(object())  # cualquier fila => revocado
    assert token_esta_revocado(db, {"jti": "x", "exp": _exp_futuro()}) is True


# ── revocar_token ────────────────────────────────────────────────────────────

def test_revocar_inserta_cuando_no_existe():
    db = _fake_db_con_first(None)   # no existe aún
    revocar_token(db, {"sub": "5", "jti": "nuevo", "exp": _exp_futuro()}, motivo="LOGOUT")
    assert db.add.called, "debe insertar una fila nueva en la blacklist"
    assert db.commit.called


def test_revocar_es_idempotente():
    db = _fake_db_con_first(object())  # ya existe esa jti
    revocar_token(db, {"sub": "5", "jti": "repetido", "exp": _exp_futuro()}, motivo="LOGOUT")
    assert not db.add.called, "no debe duplicar una jti ya revocada"
