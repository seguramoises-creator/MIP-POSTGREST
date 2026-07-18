"""Dependencies FastAPI para autorización por (accion, recurso) — Fase 2.

Reemplazan a `require_roles(...)` en los endpoints: en vez de listar roles, se declara la
intención (`require(Accion.X, Recurso.Y)`) y el motor decide contra la matriz. Denegación por
defecto: si `can()` devuelve None → 403.

- `require(accion, recurso)`   → devuelve el Usuario (drop-in del patrón `current_user=Depends(...)`).
- `autorizar(accion, recurso)` → devuelve `Autorizacion(usuario, alcance)` para endpoints que
  además necesitan el alcance para filtrar datos (own/team/all).
"""
from typing import NamedTuple

from fastapi import Depends, HTTPException, status

from app.core.deps import get_current_active_user
from app.core.authz.constantes import Accion, Alcance
from app.core.authz import engine
from app.models.usuario import Usuario


class Autorizacion(NamedTuple):
    usuario: Usuario
    alcance: Alcance


def _denegado(accion: Accion, recurso: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"Acceso denegado: no tiene permiso '{accion.value}' sobre '{recurso}'.",
    )


def require(accion: Accion, recurso: str):
    """Dependency de guard: 403 si el rol no tiene `accion` sobre `recurso`. Devuelve el Usuario."""
    def _dep(user: Usuario = Depends(get_current_active_user)) -> Usuario:
        if engine.can(user, accion, recurso) is None:
            raise _denegado(accion, recurso)
        return user
    return _dep


def autorizar(accion: Accion, recurso: str):
    """Dependency que además expone el alcance concedido (para filtrar datos en el endpoint)."""
    def _dep(user: Usuario = Depends(get_current_active_user)) -> Autorizacion:
        alcance = engine.can(user, accion, recurso)
        if alcance is None:
            raise _denegado(accion, recurso)
        return Autorizacion(user, alcance)
    return _dep


def autorizar_export(recurso_modulo: str):
    """Dependency de exportación: 403 si el usuario no puede exportar `recurso_modulo`. El alcance
    devuelto es el EFECTIVO (capado por su lectura del módulo) — el endpoint lo usa para filtrar
    los datos exportados y así el export nunca excede el alcance de lectura."""
    def _dep(user: Usuario = Depends(get_current_active_user)) -> Autorizacion:
        alcance = engine.alcance_export_modulo(user, recurso_modulo)
        if alcance is None:
            raise _denegado(Accion.EXPORT, recurso_modulo)
        return Autorizacion(user, alcance)
    return _dep
