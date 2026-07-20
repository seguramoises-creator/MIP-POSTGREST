"""SCGCPR — Política de contraseñas: complejidad por rol, expiración y no
reutilización (historial). Parámetros configurables en vivo vía config_service
(Config.DIM_Parametro). 100% Python, sin stored procedures."""
from datetime import datetime, timezone, timedelta

from sqlalchemy.orm import Session

from app.services import config_service
from app.core.security import verify_password
from app.models.usuario import Rol, PasswordHistorial

# Defaults (si el parámetro no está en Config.DIM_Parametro).
DEF_EXPIRACION_ACTIVA = True
DEF_EXPIRACION_DIAS = 90
DEF_AVISO_DIAS = 7
DEF_HISTORIAL_N = 5
DEF_MIN_LONGITUD = 8
DEF_MIN_LONGITUD_ADMIN = 12

def es_especial(c: str) -> bool:
    """¿Cuenta como carácter especial? Cualquiera que no sea letra ni dígito ni espacio.

    Antes era una lista fija ("!@#$%^&*()_+-=[]{};:,.<>?/|~") que dejaba fuera símbolos
    muy a mano en teclados móviles en español —`¿` `¡` `'` `"` `` ` ``— y en la práctica
    esos usuarios no lograban cumplir la regla. `isalnum()` es Unicode-aware, así que las
    letras acentuadas y la ñ siguen contando como LETRAS (no como especiales)."""
    return not c.isalnum() and not c.isspace()


def _rol_val(rol) -> str:
    return rol.value if hasattr(rol, "value") else str(rol)


# ── Complejidad ──────────────────────────────────────────────────────────────

def min_longitud(db: Session, rol) -> int:
    if _rol_val(rol) == Rol.ADMIN.value:
        return config_service.obtener_int(db, "PASSWORD_MIN_LONGITUD_ADMIN", DEF_MIN_LONGITUD_ADMIN)
    return config_service.obtener_int(db, "PASSWORD_MIN_LONGITUD", DEF_MIN_LONGITUD)


def validar_complejidad(db: Session, password: str, rol) -> None:
    """Lanza ValueError con mensaje claro por la primera regla incumplida."""
    n = min_longitud(db, rol)
    if len(password) < n:
        raise ValueError(f"La contraseña debe tener al menos {n} caracteres")
    if not any(c.isupper() for c in password):
        raise ValueError("Debe contener al menos una mayúscula")
    if not any(c.islower() for c in password):
        raise ValueError("Debe contener al menos una minúscula")
    if not any(c.isdigit() for c in password):
        raise ValueError("Debe contener al menos un número")
    if not any(es_especial(c) for c in password):
        raise ValueError("Debe contener al menos un carácter especial (!@#$%¿'…)")


# ── Historial (no reutilización) ─────────────────────────────────────────────

def contrasena_reutilizada(db: Session, usuario, password_plano: str) -> bool:
    """True si la nueva contraseña coincide con la actual o con las últimas N."""
    if verify_password(password_plano, usuario.hashed_password):
        return True
    n = config_service.obtener_int(db, "PASSWORD_HISTORIAL_N", DEF_HISTORIAL_N)
    if n <= 0:
        return False
    previas = (db.query(PasswordHistorial)
               .filter(PasswordHistorial.usuario_id == usuario.id)
               .order_by(PasswordHistorial.creado_en.desc())
               .limit(n).all())
    return any(verify_password(password_plano, p.hashed_password) for p in previas)


def registrar_historial(db: Session, usuario_id: int, hashed: str) -> None:
    """Guarda un hash previo y poda el historial a las últimas N filas."""
    db.add(PasswordHistorial(usuario_id=usuario_id, hashed_password=hashed))
    db.flush()
    n = config_service.obtener_int(db, "PASSWORD_HISTORIAL_N", DEF_HISTORIAL_N)
    sobrantes = (db.query(PasswordHistorial)
                 .filter(PasswordHistorial.usuario_id == usuario_id)
                 .order_by(PasswordHistorial.creado_en.desc())
                 .offset(max(0, n)).all())
    for s in sobrantes:
        db.delete(s)


# ── Estado / expiración ──────────────────────────────────────────────────────

def estado_password(db: Session, usuario) -> dict:
    """Devuelve {debe_cambiar, motivo, dias_para_expirar} según la política vigente."""
    activa = config_service.obtener_bool(db, "PASSWORD_EXPIRACION_ACTIVA", DEF_EXPIRACION_ACTIVA)
    dias_para = None
    expirada = False
    if activa and usuario.password_actualizado_en is not None:
        dias = config_service.obtener_int(db, "PASSWORD_EXPIRACION_DIAS", DEF_EXPIRACION_DIAS)
        base = usuario.password_actualizado_en
        if base.tzinfo is None:
            base = base.replace(tzinfo=timezone.utc)
        vence = base + timedelta(days=dias)
        dias_para = (vence - datetime.now(timezone.utc)).days
        expirada = dias_para < 0
    debe = bool(usuario.debe_cambiar_password) or expirada
    if usuario.debe_cambiar_password:
        motivo = "primer_login"
    elif expirada:
        motivo = "expirada"
    elif dias_para is not None and dias_para <= config_service.obtener_int(db, "PASSWORD_AVISO_DIAS", DEF_AVISO_DIAS):
        motivo = "por_expirar"
    else:
        motivo = "ok"
    return {"debe_cambiar": debe, "motivo": motivo, "dias_para_expirar": dias_para}
