"""
SCGCPR — Router: Setup inicial del sistema (primer arranque)
Público — no requiere autenticación.
Solo funciona cuando NO existen usuarios en la BD.
"""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, field_validator
import re

from app.db.database import get_db
from app.models.usuario import Usuario, Rol
from app.core.security import hash_password

router = APIRouter(prefix="/setup", tags=["setup"])


class SetupRequest(BaseModel):
    nombre_completo: str
    username: str
    email: str
    password: str

    @field_validator("password")
    @classmethod
    def validar_password(cls, v: str) -> str:
        if len(v) < 12:
            raise ValueError("La contraseña debe tener al menos 12 caracteres")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Debe contener al menos una mayúscula")
        if not re.search(r"[a-z]", v):
            raise ValueError("Debe contener al menos una minúscula")
        if not re.search(r"\d", v):
            raise ValueError("Debe contener al menos un número")
        return v


@router.get("/status")
def setup_status(db: Session = Depends(get_db)):
    """Devuelve setup_required=true si no existen usuarios en la BD."""
    total = db.query(Usuario).count()
    return {"setup_required": total == 0}


@router.post("/inicializar")
def inicializar(data: SetupRequest, db: Session = Depends(get_db)):
    """Crea el primer usuario ADMIN. Solo disponible cuando no hay usuarios."""
    total = db.query(Usuario).count()
    if total > 0:
        raise HTTPException(
            status_code=403,
            detail="El sistema ya fue inicializado. Inicia sesión con tu usuario ADMIN."
        )

    # Verificar unicidad
    if db.query(Usuario).filter(Usuario.username == data.username).first():
        raise HTTPException(status_code=400, detail="El nombre de usuario ya existe")
    if db.query(Usuario).filter(Usuario.email == data.email).first():
        raise HTTPException(status_code=400, detail="El correo ya existe")

    usuario = Usuario(
        username=data.username,
        email=data.email,
        hashed_password=hash_password(data.password),
        nombre_completo=data.nombre_completo,
        rol=Rol.ADMIN,
        activo=True,
        debe_cambiar_password=False,
        intentos_fallidos=0,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(usuario)
    db.commit()
    db.refresh(usuario)

    return {
        "ok": True,
        "mensaje": f"Usuario '{data.username}' creado correctamente. Ya puedes iniciar sesión."
    }
