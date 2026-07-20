"""
Activación de cuenta por enlace de un solo uso.

Reemplaza el envío de contraseñas temporales por correo. Al crear un usuario con correo,
el sistema le manda un enlace; el usuario abre el enlace y **crea él mismo su contraseña**.
La contraseña nunca viaja por correo, así que no queda archivada en el buzón ni en los
servidores intermedios.

Reglas:
- Token aleatorio de 256 bits (`secrets.token_urlsafe(32)`), guardado como SHA-256.
  El token en claro existe solo dentro del correo — ni en la BD ni en los logs.
- Caduca (24 h por defecto, configurable en `ACTIVACION_EXPIRA_HORAS`).
- De un solo uso: al activar se marca `usado` y se invalida cualquier otro pendiente.
- Al generar uno nuevo se invalidan los previos del mismo usuario (el último manda).
- Los mensajes hacia afuera son genéricos: nunca revelan si un correo está registrado
  ni si un token existió alguna vez.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from loguru import logger
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.models.usuario import Usuario, ActivacionCuenta
from app.services import config_service, notification_service, password_policy_service

DEF_EXPIRA_HORAS = 24


class TokenInvalidoError(Exception):
    """Token inexistente, caducado, ya usado o de un usuario inhabilitado.

    Un único error para los cuatro casos, a propósito: distinguirlos le diría a un
    atacante si un token existió, si ya se usó o a quién pertenece."""


def expira_horas(db: Session) -> int:
    return config_service.obtener_int(db, "ACTIVACION_EXPIRA_HORAS", DEF_EXPIRA_HORAS)


def _hash(token: str) -> str:
    """SHA-256 en hexadecimal (64 chars). Determinista: permite buscar por índice.
    Ver el docstring del modelo `ActivacionCuenta` para por qué no es bcrypt."""
    return hashlib.sha256((token or "").strip().encode("utf-8")).hexdigest()


def _enlace(token: str) -> str:
    base = (settings.PUBLIC_BASE_URL or "").rstrip("/")
    return f"{base}/activar/{token}"


def generar_token(db: Session, usuario: Usuario) -> str:
    """Crea un token nuevo para el usuario e invalida los anteriores. NO envía el correo.

    Devuelve el token EN CLARO: es la única vez que existe fuera del correo. No lo
    registres en logs ni lo devuelvas por la API."""
    db.query(ActivacionCuenta).filter(
        ActivacionCuenta.usuario_id == usuario.id,
        ActivacionCuenta.usado == False,                     # noqa: E712
    ).update({"usado": True, "usado_en": datetime.now(timezone.utc)})

    token = secrets.token_urlsafe(32)
    db.add(ActivacionCuenta(
        usuario_id=usuario.id,
        token_hash=_hash(token),
        expira_en=datetime.now(timezone.utc) + timedelta(hours=expira_horas(db)),
        usado=False,
    ))
    db.commit()
    return token


def enviar_activacion(db: Session, usuario: Usuario) -> bool:
    """Genera el token y envía el correo de activación. Best-effort: si el correo falla,
    el token queda creado igual y el administrador puede reenviarlo."""
    if not usuario.email:
        logger.info(f"Activación: usuario_id={usuario.id} sin correo — no se envía enlace")
        return False
    token = generar_token(db, usuario)
    enviado = notification_service.notificar_activacion_cuenta(
        destinatario=usuario.email,
        nombre=usuario.nombre_completo or usuario.username,
        username=usuario.username,
        enlace=_enlace(token),
        horas=expira_horas(db),
    )
    logger.info(f"Activación: enlace generado para usuario_id={usuario.id} (correo enviado={enviado})")
    return enviado


def validar(db: Session, token: str) -> ActivacionCuenta:
    """Comprueba que el token exista, no haya caducado, no se haya usado y pertenezca a
    un usuario habilitado. Lanza TokenInvalidoError (genérico) en cualquier otro caso."""
    if not (token or "").strip():
        raise TokenInvalidoError("El enlace no es válido o ya venció.")

    fila = (db.query(ActivacionCuenta)
            .filter(ActivacionCuenta.token_hash == _hash(token))
            .first())
    if fila is None or fila.usado:
        raise TokenInvalidoError("El enlace no es válido o ya venció.")

    expira = fila.expira_en
    if expira.tzinfo is None:
        expira = expira.replace(tzinfo=timezone.utc)
    if expira <= datetime.now(timezone.utc):
        raise TokenInvalidoError("El enlace no es válido o ya venció.")

    usuario = db.query(Usuario).filter(Usuario.id == fila.usuario_id).first()
    if usuario is None or not usuario.activo:
        raise TokenInvalidoError("El enlace no es válido o ya venció.")
    return fila


def usuario_del_token(db: Session, token: str) -> Usuario:
    """Usuario dueño de un token válido (para saludarlo por su nombre en la pantalla)."""
    fila = validar(db, token)
    return db.query(Usuario).filter(Usuario.id == fila.usuario_id).first()


def activar(db: Session, token: str, password: str, ip: str | None = None) -> Usuario:
    """Valida el token, fija la contraseña elegida por el usuario y activa la cuenta.

    Lanza TokenInvalidoError si el enlace no sirve, o ValueError si la contraseña no
    cumple la política. El token se consume aquí y no vuelve a servir."""
    fila = validar(db, token)
    usuario = db.query(Usuario).filter(Usuario.id == fila.usuario_id).first()

    # La política se valida ANTES de consumir el token: si la contraseña es débil, el
    # usuario debe poder reintentar con el mismo enlace en vez de quedarse fuera.
    password_policy_service.validar_complejidad(db, password, usuario.rol)

    ahora = datetime.now(timezone.utc)
    password_policy_service.registrar_historial(db, usuario.id, usuario.hashed_password)
    usuario.hashed_password = hash_password(password)
    usuario.password_actualizado_en = ahora
    usuario.activado_en = ahora
    # Ya fijó su propia contraseña: no tiene sentido pedirle que la cambie al entrar.
    usuario.debe_cambiar_password = False
    usuario.intentos_fallidos = 0
    usuario.bloqueado_hasta = None

    fila.usado = True
    fila.usado_en = ahora
    fila.usado_ip = ip
    # Cualquier otro enlace pendiente del usuario queda inservible.
    db.query(ActivacionCuenta).filter(
        ActivacionCuenta.usuario_id == usuario.id,
        ActivacionCuenta.usado == False,                     # noqa: E712
    ).update({"usado": True, "usado_en": ahora})
    db.commit()
    logger.info(f"Activación: cuenta activada usuario_id={usuario.id} ip={ip}")
    return usuario


def reenviar_por_email(db: Session, email: str) -> bool:
    """Reenvía el enlace a un usuario que aún no ha activado su cuenta.

    Devuelve True si se envió (para el log interno). El endpoint responde igual en
    todos los casos: nunca revela si el correo existe ni en qué estado está la cuenta."""
    if not (email or "").strip():
        return False
    usuario = (db.query(Usuario)
               .filter(func.lower(Usuario.email) == email.strip().lower(),
                       Usuario.activo == True)               # noqa: E712
               .first())
    if usuario is None:
        logger.info(f"Reenvío de activación: correo no registrado ({email!r}) — respuesta genérica")
        return False
    if usuario.activado_en is not None:
        # Ya activada: reenviar un enlace permitiría cambiar la contraseña a cualquiera que
        # conozca el correo. Para eso está "¿Olvidó su contraseña?", que sí exige el código.
        logger.info(f"Reenvío de activación: usuario_id={usuario.id} ya está activado — no se envía")
        return False
    return enviar_activacion(db, usuario)
