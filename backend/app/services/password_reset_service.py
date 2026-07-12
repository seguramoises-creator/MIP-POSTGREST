"""
Recuperación de contraseña por código ("Olvidó su contraseña").

Reglas (spec):
- El código es aleatorio (6 dígitos), se guarda HASHEADO (bcrypt), expira
  (`EXPIRA_MINUTOS`) y es de un solo uso.
- Al solicitar un código nuevo se invalidan los previos del usuario.
- Máx. `MAX_INTENTOS` validaciones fallidas antes de invalidar el código.
- Los mensajes al exterior son genéricos: nunca se revela si el correo existe.
"""
from __future__ import annotations
import secrets
from datetime import datetime, timedelta, timezone

from loguru import logger
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.models.usuario import Usuario, PasswordResetCode
from app.services import password_policy_service, notification_service

EXPIRA_MINUTOS = 15
MAX_INTENTOS = 5


class CodigoInvalidoError(Exception):
    """Código inexistente, expirado, ya usado o con demasiados intentos."""


def _usuario_por_email(db: Session, email: str) -> Usuario | None:
    if not email:
        return None
    return (db.query(Usuario)
            .filter(func.lower(Usuario.email) == email.strip().lower(), Usuario.activo == True)  # noqa: E712
            .first())


def solicitar_codigo(db: Session, email: str) -> bool:
    """Genera y envía un código si el correo corresponde a un usuario activo.
    Retorna True si se envió (para logs internos); el endpoint responde genérico
    en cualquier caso, sin revelar si el correo existe."""
    usuario = _usuario_por_email(db, email)
    if not usuario:
        logger.info(f"Recuperación: correo no registrado o inactivo ({email!r}) — respuesta genérica")
        return False

    # Invalida cualquier código previo sin usar del mismo usuario.
    db.query(PasswordResetCode).filter(
        PasswordResetCode.usuario_id == usuario.id, PasswordResetCode.usado == False  # noqa: E712
    ).update({"usado": True})

    codigo = f"{secrets.randbelow(1_000_000):06d}"  # 000000–999999
    reset = PasswordResetCode(
        usuario_id=usuario.id,
        codigo_hash=hash_password(codigo),
        expira_en=datetime.now(timezone.utc) + timedelta(minutes=EXPIRA_MINUTOS),
        usado=False, intentos=0,
    )
    db.add(reset)
    db.commit()
    enviado = notification_service.notificar_codigo_recuperacion(
        usuario.email, usuario.nombre_completo, codigo, EXPIRA_MINUTOS)
    logger.info(f"Recuperación: código generado para usuario_id={usuario.id} (email enviado={enviado})")
    return True


def restablecer(db: Session, email: str, codigo: str, password_nuevo: str) -> Usuario:
    """Valida el código y, si es correcto y vigente, fija la nueva contraseña.
    Lanza CodigoInvalidoError (genérico) o ValueError (complejidad/reutilización)."""
    usuario = _usuario_por_email(db, email)
    if not usuario:
        raise CodigoInvalidoError("Código inválido o expirado.")

    ahora = datetime.now(timezone.utc)
    reset = (db.query(PasswordResetCode)
             .filter(PasswordResetCode.usuario_id == usuario.id,
                     PasswordResetCode.usado == False,          # noqa: E712
                     PasswordResetCode.expira_en > ahora)
             .order_by(PasswordResetCode.creado_en.desc())
             .first())
    if not reset:
        raise CodigoInvalidoError("Código inválido o expirado.")

    if reset.intentos >= MAX_INTENTOS:
        reset.usado = True
        db.commit()
        raise CodigoInvalidoError("Código inválido o expirado.")

    if not verify_password((codigo or "").strip(), reset.codigo_hash):
        reset.intentos += 1
        if reset.intentos >= MAX_INTENTOS:
            reset.usado = True
        db.commit()
        raise CodigoInvalidoError("Código inválido o expirado.")

    # Código correcto → aplica la política de contraseña y guarda.
    password_policy_service.validar_complejidad(db, password_nuevo, usuario.rol)
    if password_policy_service.contrasena_reutilizada(db, usuario, password_nuevo):
        raise ValueError("No puedes reutilizar una contraseña reciente")
    password_policy_service.registrar_historial(db, usuario.id, usuario.hashed_password)

    usuario.hashed_password = hash_password(password_nuevo)
    usuario.password_actualizado_en = ahora
    usuario.debe_cambiar_password = False
    # Consume ESTE código y cualquier otro pendiente del usuario (no reutilizable).
    db.query(PasswordResetCode).filter(
        PasswordResetCode.usuario_id == usuario.id, PasswordResetCode.usado == False  # noqa: E712
    ).update({"usado": True})
    db.commit()
    logger.info(f"Recuperación: contraseña restablecida para usuario_id={usuario.id}")
    return usuario
