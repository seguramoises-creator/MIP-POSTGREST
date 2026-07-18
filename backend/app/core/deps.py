"""
SCGCPR — Dependencies de FastAPI
Inyección de usuario autenticado y control RBAC.
"""
from datetime import timezone
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.security import decode_token
from app.db.database import get_db
from app.models.usuario import Usuario, Rol

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Session = Depends(get_db),
) -> Usuario:
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No se pudo validar las credenciales",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(token)
        user_id: str = payload.get("sub")
        if not user_id:
            raise credentials_exc
    except JWTError:
        raise credentials_exc

    user = db.query(Usuario).filter(Usuario.id == int(user_id), Usuario.activo == True).first()
    if not user:
        raise credentials_exc

    # RBAC Fase 1 — revocación por cambio de rol: un access token emitido ANTES de
    # roles_actualizado_en ya no es válido (sus permisos podrían haber cambiado).
    ra = getattr(user, "roles_actualizado_en", None)
    if ra is not None:
        if ra.tzinfo is None:
            ra = ra.replace(tzinfo=timezone.utc)
        iat = payload.get("iat")
        if iat is None or iat < int(ra.timestamp()):
            raise credentials_exc

    return user


def get_current_active_user(
    current_user: Annotated[Usuario, Depends(get_current_user)],
) -> Usuario:
    if not current_user.activo:
        raise HTTPException(status_code=400, detail="Usuario inactivo")
    return current_user


# ── Helpers RBAC ─────────────────────────────────────────────────────────────

def require_roles(*roles: str):
    """Factory que genera un dependency que exige uno de los roles dados."""
    def _checker(user: Annotated[Usuario, Depends(get_current_active_user)]) -> Usuario:
        if user.rol not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Acceso denegado. Roles requeridos: {', '.join(roles)}",
            )
        return user
    return _checker


# ── Shortcuts por rol ────────────────────────────────────────────────────────

RequireAdmin        = Depends(require_roles(Rol.ADMIN))
RequirePresidencia  = Depends(require_roles(Rol.ADMIN, Rol.PRESIDENCIA))
RequireDirComercial = Depends(require_roles(Rol.ADMIN, Rol.PRESIDENCIA, Rol.DIR_COMERCIAL))
RequireGerente      = Depends(require_roles(Rol.ADMIN, Rol.PRESIDENCIA, Rol.DIR_COMERCIAL, Rol.GERENTE_PRODUCTIVIDAD, Rol.GERENTE_DISTRITO, Rol.GERENTE_MARCA))
RequireAnyAuth      = Depends(get_current_active_user)
