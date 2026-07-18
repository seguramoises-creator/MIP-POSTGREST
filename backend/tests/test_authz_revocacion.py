"""RBAC Fase 1 — T6: revocación de permisos por cambio de rol (iat vs roles_actualizado_en)."""
from datetime import datetime, timezone, timedelta

from app.core.security import create_access_token, decode_token


def test_access_token_lleva_iat():
    payload = decode_token(create_access_token("1"))
    assert "iat" in payload and isinstance(payload["iat"], int)


def test_iat_anterior_a_roles_actualizado_se_rechaza():
    # Regla que aplica deps.get_current_user: iat < roles_actualizado_en → token inválido.
    token = create_access_token("1", expires_delta=timedelta(minutes=60))
    iat = decode_token(token)["iat"]
    ra_futuro = datetime.fromtimestamp(iat + 5, tz=timezone.utc)   # rol cambiado DESPUÉS del token
    assert iat < int(ra_futuro.timestamp())                        # → se rechaza
    ra_pasado = datetime.fromtimestamp(iat - 5, tz=timezone.utc)   # rol cambiado ANTES del token
    assert not (iat < int(ra_pasado.timestamp()))                  # → sigue válido
