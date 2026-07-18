"""RBAC — contrato de autorización para el frontend + inspección de la matriz (solo ADMIN).

`GET /authz/me/permisos` es la ÚNICA fuente de la que el frontend deriva navegación y controles
(mata las 3 copias App/Sidebar/ProtectedRoute). El backend sigue siendo la autoridad: ocultar un
control no sustituye el guard del servidor.
"""
from fastapi import APIRouter, Depends

from app.core.deps import get_current_active_user, require_roles
from app.core.authz.constantes import Accion, RECURSOS_META
from app.core.authz import engine
from app.models.usuario import Rol, Usuario

router = APIRouter(prefix="/authz", tags=["Autorización"])

RequireAdmin = Depends(require_roles(Rol.ADMIN))

_ACCIONES = [Accion.READ, Accion.REGISTER, Accion.CONFIGURE,
             Accion.APPROVE, Accion.EXPORT, Accion.ADMIN]


@router.get("/me/permisos", summary="Permisos efectivos del usuario actual (contrato frontend)")
def mis_permisos(current_user: Usuario = Depends(get_current_active_user)):
    """{recurso: {accion: alcance, ...}} solo para lo concedido. Incluye `export_efectivo` por
    módulo (capado por la lectura). El frontend deriva menú/rutas/botones de aquí."""
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
def ver_matriz():
    """Inspección/auditoría de la matriz canónica completa."""
    from app.core.authz.matrix import MATRIZ
    recursos = []
    for recurso, (nombre, modulo) in RECURSOS_META.items():
        roles = {}
        for rol, celda in MATRIZ[recurso].items():
            roles[rol.value] = None if celda is None else {
                "accion": celda[0].value, "alcance": celda[1].value}
        recursos.append({"recurso": recurso, "nombre": nombre, "modulo": modulo, "roles": roles})
    return {"recursos": recursos}
