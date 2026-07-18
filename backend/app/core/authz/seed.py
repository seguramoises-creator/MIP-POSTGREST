"""Siembra idempotente de la matriz canónica (matrix.MATRIZ) a Security.DIM_Recurso /
FACT_RolPermiso. Re-ejecutable: inserta lo faltante, actualiza lo que cambió y borra las filas
que ya no están en la matriz, de modo que la BD refleje exactamente el código.

FACT_RolPermiso guarda SOLO la celda base de cada (rol, recurso) — no la implicación de read —
porque el motor deriva la implicación en runtime; así la BD == matriz literal (auditable).
"""
from loguru import logger
from sqlalchemy.orm import Session

from app.core.authz.constantes import RECURSOS_META
from app.core.authz.matrix import MATRIZ
from app.models.seguridad_rbac import Recurso, RolPermiso


def seed_recursos(db: Session) -> int:
    """Upsert de los 28 recursos. Devuelve cuántos se insertaron nuevos."""
    existentes = {r.slug: r for r in db.query(Recurso).all()}
    nuevos = 0
    for slug, (nombre, modulo) in RECURSOS_META.items():
        r = existentes.get(slug)
        if r is None:
            db.add(Recurso(slug=slug, nombre=nombre, modulo=modulo))
            nuevos += 1
        elif (r.nombre, r.modulo) != (nombre, modulo):
            r.nombre, r.modulo = nombre, modulo
    db.flush()
    return nuevos


def seed_permisos(db: Session) -> int:
    """Sincroniza FACT_RolPermiso con la matriz. Devuelve el número de cambios (insert+update+delete)."""
    deseado = {}  # (rol, recurso, accion) -> alcance
    for recurso, fila in MATRIZ.items():
        for rol, celda in fila.items():
            if celda is None:
                continue
            accion, alcance = celda
            deseado[(rol.value, recurso, accion.value)] = alcance.value

    actuales = {(p.rol, p.recurso, p.accion): p for p in db.query(RolPermiso).all()}
    cambios = 0

    for (rol, recurso, accion), alcance in deseado.items():
        p = actuales.get((rol, recurso, accion))
        if p is None:
            db.add(RolPermiso(rol=rol, recurso=recurso, accion=accion, alcance=alcance))
            cambios += 1
        elif p.alcance != alcance:
            p.alcance = alcance
            cambios += 1

    for llave, p in actuales.items():
        if llave not in deseado:
            db.delete(p)
            cambios += 1

    db.flush()
    return cambios


def sembrar_todo(db: Session) -> dict:
    nr = seed_recursos(db)
    np = seed_permisos(db)
    db.commit()
    logger.info(f"[authz.seed] recursos_nuevos={nr}, permisos_cambios={np}")
    return {"recursos_nuevos": nr, "permisos_cambios": np}
