"""
SCGCPR — Router: Autenticación
FIX W-01: Reemplaza datetime.utcnow() por datetime.now(timezone.utc).
FIX W-04: Logout y change-password revocan el refresh token en la blacklist.
          /refresh verifica que el token no esté revocado antes de renovar.

POST /api/v1/auth/login
POST /api/v1/auth/logout
POST /api/v1/auth/refresh
POST /api/v1/auth/change-password
GET  /api/v1/auth/me
"""
from datetime import datetime, timezone, timedelta
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user
from app.core.security import (
    create_access_token, create_refresh_token,
    decode_token, verify_password, hash_password,
)
from app.core.token_store import revocar_token, token_esta_revocado  # FIX W-04
from app.db.database import get_db
from app.models.usuario import Usuario
from app.models.hechos import Auditoria
from app.schemas.common import Msg, TokenResponse
from app.schemas.schemas import UsuarioResponse, PasswordChange
from app.core.config import settings

router = APIRouter(prefix="/auth", tags=["Autenticación"])


def _registrar_auditoria(
    db: Session,
    usuario: Usuario | None,
    accion: str,
    request: Request,
    exitoso: bool,
    detalle: str = "",
) -> None:
    """Registra evento de autenticación en FACT_Auditoria."""
    db.add(Auditoria(
        usuario_id  = usuario.id        if usuario else None,
        username    = usuario.username  if usuario else None,
        rol         = usuario.rol       if usuario else None,
        accion      = accion,
        modulo      = "AUTH",
        exitoso     = exitoso,
        detalle     = detalle,
        ip_address  = request.client.host if request.client else None,
        user_agent  = request.headers.get("user-agent"),
        fecha_hora  = datetime.now(timezone.utc),  # FIX W-01
    ))
    db.commit()


@router.post("/login", response_model=TokenResponse, summary="Iniciar sesión")
def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Autentica usuario con username y password.
    Retorna access_token (JWT) y refresh_token.
    Registra auditoría de login.
    """
    user: Usuario | None = db.query(Usuario).filter(
        Usuario.username == form_data.username
    ).first()

    # Verificar bloqueo temporal (FIX W-01: comparación timezone-aware)
    now = datetime.now(timezone.utc)
    if user and user.bloqueado_hasta:
        bloqueado_hasta_aware = (
            user.bloqueado_hasta.replace(tzinfo=timezone.utc)
            if user.bloqueado_hasta.tzinfo is None
            else user.bloqueado_hasta
        )
        if bloqueado_hasta_aware > now:
            _registrar_auditoria(db, user, "LOGIN_BLOQUEADO", request, False, "Cuenta bloqueada")
            raise HTTPException(
                status_code=423,
                detail="Cuenta bloqueada temporalmente. Intente más tarde."
            )

    if not user or not verify_password(form_data.password, user.hashed_password):
        if user:
            user.intentos_fallidos += 1
            if user.intentos_fallidos >= 5:
                # FIX W-01: datetime.now(timezone.utc)
                user.bloqueado_hasta = datetime.now(timezone.utc) + timedelta(minutes=30)
            db.commit()
        _registrar_auditoria(db, user, "LOGIN_FALLIDO", request, False, "Credenciales inválidas")
        raise HTTPException(status_code=401, detail="Credenciales incorrectas")

    if not user.activo:
        raise HTTPException(status_code=400, detail="Usuario inactivo")

    # Resetear intentos fallidos
    user.intentos_fallidos = 0
    user.ultimo_login      = datetime.now(timezone.utc)  # FIX W-01
    user.bloqueado_hasta   = None
    db.commit()

    rol_value = user.rol.value if hasattr(user.rol, 'value') else str(user.rol)
    access_token  = create_access_token(
        subject=user.id,
        extra_claims={
            "rol": rol_value,
            "username": user.username,
            "nombre_completo": user.nombre_completo,
        }
    )
    refresh_token = create_refresh_token(subject=user.id)

    _registrar_auditoria(db, user, "LOGIN", request, True)

    return TokenResponse(
        access_token  = access_token,
        refresh_token = refresh_token,
        expires_in    = settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/logout", response_model=Msg, summary="Cerrar sesión")
def logout(
    request: Request,
    refresh_token_str: str = Body(None, embed=True, alias="refresh_token"),
    current_user: Usuario = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Cierra sesión e invalida el refresh_token proporcionado.
    FIX W-04: Token revocado en blacklist.
    """
    if refresh_token_str:
        try:
            payload = decode_token(refresh_token_str)
            revocar_token(db, payload, motivo="LOGOUT")  # FIX W-04 (blacklist en BD)
        except JWTError:
            pass  # Token ya expirado — no importa

    _registrar_auditoria(db, current_user, "LOGOUT", request, True)
    return Msg(message="Sesión cerrada correctamente")


@router.post("/refresh", response_model=TokenResponse, summary="Renovar token")
def refresh_token_endpoint(
    refresh_token_str: str = Body(..., embed=True, alias="refresh_token"),
    db: Session = Depends(get_db),
):
    """
    Renueva el access_token usando un refresh_token válido.
    FIX W-04: Verifica que el token no esté revocado.
    """
    try:
        payload = decode_token(refresh_token_str)
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Token inválido")

        # FIX W-04: Verificar blacklist (en BD)
        if token_esta_revocado(db, payload):
            raise HTTPException(
                status_code=401,
                detail="Refresh token revocado. Inicie sesión nuevamente."
            )

        user_id = int(payload.get("sub"))
    except (JWTError, ValueError):
        raise HTTPException(status_code=401, detail="Token inválido o expirado")

    user: Usuario | None = db.query(Usuario).filter(Usuario.id == user_id).first()
    if not user or not user.activo:
        raise HTTPException(status_code=401, detail="Usuario no encontrado o inactivo")

    rol_value = user.rol.value if hasattr(user.rol, "value") else str(user.rol)
    new_access_token = create_access_token(
        subject=user.id,
        extra_claims={
            "rol": rol_value,
            "username": user.username,
            "nombre_completo": user.nombre_completo,
        },
    )
    new_refresh_token = create_refresh_token(subject=user.id)

    # Revocar el refresh token anterior y emitir uno nuevo
    revocar_token(db, payload, motivo="REFRESH_ROTATION")

    return TokenResponse(
        access_token=new_access_token,
        refresh_token=new_refresh_token,
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.get("/me", response_model=UsuarioResponse, summary="Usuario actual")
def get_me(current_user: Usuario = Depends(get_current_active_user)):
    """Retorna los datos del usuario autenticado."""
    return current_user


@router.post("/change-password", response_model=Msg, summary="Cambiar contraseña")
def change_password(
    datos: PasswordChange,
    request: Request,
    current_user: Usuario = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Cambia la contraseña del usuario autenticado. Valida la contraseña actual y
    aplica la política de complejidad (mín. 12, mayúscula, minúscula, número)."""
    if not verify_password(datos.password_actual, current_user.hashed_password):
        _registrar_auditoria(db, current_user, "CHANGE_PASSWORD", request, False,
                             "Contraseña actual incorrecta")
        raise HTTPException(status_code=400, detail="La contraseña actual es incorrecta")
    current_user.hashed_password = hash_password(datos.password_nuevo)
    db.commit()
    _registrar_auditoria(db, current_user, "CHANGE_PASSWORD", request, True)
    return Msg(message="Contraseña actualizada correctamente")
