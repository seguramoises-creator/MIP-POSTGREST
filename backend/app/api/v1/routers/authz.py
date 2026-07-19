"""RBAC — contrato de autorización para el frontend + inspección/EDICIÓN de la matriz (solo ADMIN).

`GET /authz/me/permisos` es la ÚNICA fuente de la que el frontend deriva navegación y controles.
La matriz es EDITABLE desde la UI: vive en `Security.FACT_RolPermiso` (fuente de verdad en runtime,
con caché en `app.core.authz.runtime`); `matrix.py` queda como valores de fábrica. El backend sigue
siendo la autoridad: ocultar un control no sustituye el guard del servidor.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, require_roles
from app.core.authz.constantes import Accion, RECURSOS_META
from app.core.authz import engine, runtime, edicion
from app.db.database import get_db
from app.models.usuario import Rol, Usuario

router = APIRouter(prefix="/authz", tags=["Autorización"])

RequireAdmin = Depends(require_roles(Rol.ADMIN))

_ACCIONES = [Accion.READ, Accion.REGISTER, Accion.CONFIGURE,
             Accion.APPROVE, Accion.EXPORT, Accion.ADMIN]

# Roles que NO se pueden editar desde la UI (Superadmin conserva acceso total).
ROLES_NO_EDITABLES = [Rol.ADMIN.value]


class CambioPermiso(BaseModel):
    rol: str
    recurso: str
    accion: str | None = None   # None = denegar (borra la celda)
    alcance: str | None = None  # own | team | all (requerido si hay acción)


class CambiosPayload(BaseModel):
    cambios: list[CambioPermiso]


@router.get("/me/permisos", summary="Permisos efectivos del usuario actual (contrato frontend)")
def mis_permisos(current_user: Usuario = Depends(get_current_active_user),
                 db: Session = Depends(get_db)):
    """{recurso: {accion: alcance, ...}} solo para lo concedido. Incluye `export_efectivo` por
    módulo (capado por la lectura). El frontend deriva menú/rutas/botones de aquí."""
    runtime.refrescar_si_cambio(db)
    permisos = {}
    for recurso in RECURSOS_META:
        caps = {}
        for accion in _ACCIONES:
            alc = engine.can(current_user, accion, recurso)
            if alc is not None:
                caps[accion.value] = alc.value
        exp = engine.alcance_export_modulo(current_user, recurso)
        if exp is not None:
            caps["export_efectivo"] = exp.value
        if caps:
            permisos[recurso] = caps
    return {"rol": current_user.rol.value, "permisos": permisos}


@router.get("/matriz", dependencies=[RequireAdmin],
            summary="Matriz completa de autorización (solo ADMIN)")
def ver_matriz(db: Session = Depends(get_db)):
    """Inspección de la matriz vigente (BD). `roles_no_editables` marca la columna Superadmin."""
    runtime.refrescar_si_cambio(db)
    return {
        "recursos": edicion.matriz_actual(db),
        "roles": edicion.ROLES,
        "roles_no_editables": ROLES_NO_EDITABLES,
    }


@router.put("/matriz", dependencies=[RequireAdmin],
            summary="Guardar cambios en la matriz (solo ADMIN, auditado)")
def guardar_matriz(payload: CambiosPayload,
                   current_user: Usuario = Depends(get_current_active_user),
                   db: Session = Depends(get_db)):
    """Aplica las celdas modificadas (en caliente). La columna Superadmin no es editable."""
    try:
        n = edicion.aplicar_cambios(db, current_user, [c.model_dump() for c in payload.cambios])
    except edicion.CambioInvalidoError as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return {"aplicados": n, "recursos": edicion.matriz_actual(db),
            "roles": edicion.ROLES, "roles_no_editables": ROLES_NO_EDITABLES}


@router.post("/matriz/restablecer", dependencies=[RequireAdmin],
             summary="Restablecer la matriz a valores de fábrica (solo ADMIN, auditado)")
def restablecer_matriz(current_user: Usuario = Depends(get_current_active_user),
                       db: Session = Depends(get_db)):
    """Devuelve todos los permisos a los valores de código (matrix.py)."""
    res = edicion.restablecer(db, current_user)
    return {"restablecido": res, "recursos": edicion.matriz_actual(db),
            "roles": edicion.ROLES, "roles_no_editables": ROLES_NO_EDITABLES}
