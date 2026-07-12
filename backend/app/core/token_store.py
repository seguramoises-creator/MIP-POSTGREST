"""
SCGCPR — Token Blacklist (Revocación de Refresh Tokens) — persistida en BD.

FIX W-04 (v2): la blacklist vive ahora en la base de datos (tabla
`Security.FACT_TokenRevocado`) en vez de un `set` en memoria. La versión en
memoria no se compartía entre workers de uvicorn —un logout en un proceso no
revocaba el token en los demás— y se perdía al reiniciar. Persistir en BD hace
la revocación consistente entre todos los workers y duradera.

Mecanismo:
  - Logout / rotación de refresh / cambio de contraseña → `revocar_token(db, payload)`.
  - `/auth/refresh` verifica con `token_esta_revocado(db, payload)` antes de renovar.
  - Las filas cuyo token ya expiró se purgan oportunamente (`purgar_expirados`).

Nota: no hace falta comprobar expiración al verificar revocación. `decode_token`
ya rechaza tokens expirados (claim `exp`) antes de llegar aquí; por tanto, si el
`jti` está en la tabla, el token está revocado.
"""
from datetime import datetime, timezone, timedelta

from loguru import logger
from sqlalchemy.orm import Session

from app.models.usuario import TokenRevocado


def _jti_de(token_payload: dict) -> str:
    """
    Identificador único del token. Usa el claim `jti` si existe; si no
    (tokens emitidos antes de añadir el claim), cae a `sub:exp`.
    """
    return token_payload.get("jti") or f"{token_payload.get('sub')}:{token_payload.get('exp')}"


def _expira_en(token_payload: dict) -> datetime:
    exp_ts = token_payload.get("exp")
    if exp_ts:
        return datetime.fromtimestamp(exp_ts, tz=timezone.utc)
    return datetime.now(timezone.utc) + timedelta(days=7)


def _usuario_id(token_payload: dict) -> int | None:
    try:
        return int(token_payload.get("sub"))
    except (TypeError, ValueError):
        return None


def revocar_token(db: Session, token_payload: dict, motivo: str = "LOGOUT") -> None:
    """
    Revoca un token insertándolo en la blacklist. Idempotente: si el `jti`
    ya está revocado no duplica. Purga oportunamente filas expiradas para
    acotar el tamaño de la tabla.
    """
    jti = _jti_de(token_payload)

    ya_existe = db.query(TokenRevocado).filter(TokenRevocado.jti == jti).first()
    if ya_existe is not None:
        return

    db.add(TokenRevocado(
        jti        = jti,
        usuario_id = _usuario_id(token_payload),
        motivo     = motivo,
        expira_en  = _expira_en(token_payload),
    ))
    db.commit()
    logger.debug(f"Token {jti[:12]}... revocado ({motivo})")

    purgar_expirados(db)


def token_esta_revocado(db: Session, token_payload: dict) -> bool:
    """True si el `jti` del token está en la blacklist."""
    jti = _jti_de(token_payload)
    return db.query(TokenRevocado).filter(TokenRevocado.jti == jti).first() is not None


def purgar_expirados(db: Session) -> int:
    """
    Elimina de la blacklist las filas cuyo token ya expiró de forma natural
    (ya no aportan nada: un token expirado se rechaza por su claim `exp`).
    Retorna la cantidad de filas eliminadas.
    """
    ahora = datetime.now(timezone.utc)
    eliminadas = (
        db.query(TokenRevocado)
        .filter(TokenRevocado.expira_en < ahora)
        .delete(synchronize_session=False)
    )
    db.commit()
    if eliminadas:
        logger.debug(f"Blacklist: {eliminadas} tokens expirados purgados")
    return eliminadas
