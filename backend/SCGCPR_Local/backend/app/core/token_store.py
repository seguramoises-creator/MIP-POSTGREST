"""
SCGCPR — Token Blacklist (Revocación de Refresh Tokens)
FIX W-04: Implementa revocación de refresh tokens usando un set en memoria
          con TTL automático. En producción se debe migrar a Redis.

Mecanismo:
  - Al hacer logout o cambio de contraseña se agrega el JTI del token a la blacklist.
  - Al usar /auth/refresh se verifica que el token no esté revocado.
  - Los tokens expirados se limpian automáticamente cada 1h.
"""
import threading
from datetime import datetime, timezone, timedelta
from typing import Set, Dict

from loguru import logger


class TokenBlacklist:
    """
    Blacklist de refresh tokens en memoria.
    Thread-safe para uso con múltiples workers de uvicorn.
    En producción reemplazar con RedisTokenBlacklist.
    """

    def __init__(self) -> None:
        self._lock:  threading.Lock              = threading.Lock()
        self._store: Dict[str, datetime]         = {}  # jti → expira_en
        self._cleanup_interval: int              = 3600  # segundos
        self._start_cleanup_thread()

    def add(self, jti: str, expires_at: datetime) -> None:
        """Agrega un token revocado a la blacklist."""
        with self._lock:
            self._store[jti] = expires_at
        logger.debug(f"Token {jti[:8]}... revocado hasta {expires_at}")

    def is_revoked(self, jti: str) -> bool:
        """Verifica si un token está revocado."""
        with self._lock:
            exp = self._store.get(jti)
            if exp is None:
                return False
            if datetime.now(timezone.utc) > exp:
                del self._store[jti]  # expiró, limpiarlo
                return False
            return True

    def _cleanup(self) -> None:
        """Elimina tokens expirados de la blacklist."""
        now = datetime.now(timezone.utc)
        with self._lock:
            expired = [jti for jti, exp in self._store.items() if now > exp]
            for jti in expired:
                del self._store[jti]
        if expired:
            logger.debug(f"TokenBlacklist: {len(expired)} tokens expirados eliminados")

    def _start_cleanup_thread(self) -> None:
        def _loop():
            import time
            while True:
                time.sleep(self._cleanup_interval)
                self._cleanup()
        t = threading.Thread(target=_loop, daemon=True)
        t.start()

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._store)


# Singleton global — compartido entre todos los requests del proceso
token_blacklist = TokenBlacklist()


def revocar_token(token_payload: dict) -> None:
    """
    Revoca un token agregándolo a la blacklist.
    El JTI (JWT ID) se usa como clave. Si el token no tiene JTI
    se usa 'sub:exp' como identificador único.
    """
    from datetime import timedelta
    jti     = token_payload.get("jti") or f"{token_payload.get('sub')}:{token_payload.get('exp')}"
    exp_ts  = token_payload.get("exp")
    exp_dt  = (
        datetime.fromtimestamp(exp_ts, tz=timezone.utc)
        if exp_ts
        else datetime.now(timezone.utc) + timedelta(days=7)
    )
    token_blacklist.add(jti, exp_dt)


def token_esta_revocado(token_payload: dict) -> bool:
    jti = token_payload.get("jti") or f"{token_payload.get('sub')}:{token_payload.get('exp')}"
    return token_blacklist.is_revoked(jti)
