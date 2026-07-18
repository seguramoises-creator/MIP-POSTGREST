"""Filtros de alcance de datos (ABAC own/team/all) y guard anti-IDOR por registro.

Se usa junto con `engine.can(...)`: primero el motor decide el alcance, luego estas funciones
lo traducen a un filtro de `rm_id`. En Fase 2 los endpoints aplicarán estos filtros a sus queries;
en Fase 1 quedan disponibles y probados (no se cablean aún).

Reemplaza y generaliza `app/core/scope_gd.py` (que solo cubría GERENTE_DISTRITO por anonimización).
`scope_gd.py` se conserva intacto hasta la Fase 2.
"""
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.authz.constantes import Alcance
from app.models.dimensiones import RepresentanteMedico


def rm_ids_de_equipo(db: Session, gerente_id) -> set[int]:
    """IDs de los RM del equipo de un gerente (mismo gerente_id). Vacío si no tiene gerente_id."""
    if not gerente_id:
        return set()
    return {r[0] for r in db.query(RepresentanteMedico.id)
            .filter(RepresentanteMedico.gerente_id == gerente_id).all()}


def rm_ids_visibles(db: Session, user, alcance: Alcance) -> set[int] | None:
    """Conjunto de `rm_id` que el usuario puede ver con este alcance. `None` = sin filtro (todos).

    - ALL  → None (no filtrar).
    - OWN  → {user.rm_id} (o vacío si no tiene rm_id).
    - TEAM → RMs del equipo del gerente (via user.gerente_id).
    - NONE → conjunto vacío.
    """
    if alcance == Alcance.ALL:
        return None
    if alcance == Alcance.OWN:
        rm_id = getattr(user, "rm_id", None)
        return {rm_id} if rm_id else set()
    if alcance == Alcance.TEAM:
        return rm_ids_de_equipo(db, getattr(user, "gerente_id", None))
    return set()


def assert_ve_rm(user, rm_id: int, alcance: Alcance, ids_equipo: set[int] | None = None) -> None:
    """Guard por registro (anti-IDOR/BOLA): 403 si el usuario no puede ver ese `rm_id`.

    - ALL  → siempre permitido.
    - OWN  → permitido solo si `user.rm_id == rm_id`.
    - TEAM → permitido solo si `rm_id in ids_equipo` (el caller precomputa `ids_equipo` con
             `rm_ids_visibles(db, user, TEAM)` para no consultar por cada registro).
    """
    if alcance == Alcance.ALL:
        return
    if alcance == Alcance.OWN and getattr(user, "rm_id", None) == rm_id:
        return
    if alcance == Alcance.TEAM and ids_equipo is not None and rm_id in ids_equipo:
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                        detail="No autorizado sobre ese registro")
