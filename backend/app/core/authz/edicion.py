"""Edición de la matriz RBAC desde la UI (solo ADMIN, auditada).

Escribe la celda base en `FACT_RolPermiso` (1 fila por (rol,recurso)); el motor deriva en runtime
la implicación de read y el alcance de export. Salvaguardas: la columna ADMIN es inmutable y la
acción `admin` no es asignable desde la UI. Cada cambio y cada restablecimiento se auditan.
"""
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.authz.constantes import Accion, RECURSOS_META, RECURSOS
from app.core.authz.matrix import MATRIZ
from app.core.authz import runtime, seed
from app.core.authz.audit import registrar_evento_seguridad
from app.models.seguridad_rbac import RolPermiso
from app.models.usuario import Rol

_ROLES_VALIDOS = {r.value for r in Rol}
_ACCIONES_VALIDAS = {a.value for a in Accion}
_ALCANCES_VALIDOS = {"own", "team", "linea", "all"}

# Orden canónico de columnas (10 de la matriz + 3 derivados) para el contrato del GET.
_ROLES_ORDEN = [
    Rol.REPRESENTANTE_MEDICO, Rol.GERENTE_DISTRITO, Rol.GERENTE_MARCA, Rol.GERENTE_MARKETING,
    Rol.GERENTE_PRODUCTIVIDAD, Rol.GERENTE_MEDICO, Rol.PRESIDENCIA, Rol.ANALISTA_DATOS,
    Rol.FINANZAS, Rol.ADMIN, Rol.CAPACITACION, Rol.DIR_COMERCIAL, Rol.CONSULTA,
]
ROLES = [r.value for r in _ROLES_ORDEN]


class CambioInvalidoError(ValueError):
    """Un cambio no pasó validación (rol/recurso/acción/alcance inválidos o columna ADMIN)."""


def _validar(cambio: dict):
    rol = cambio.get("rol")
    recurso = cambio.get("recurso")
    accion = cambio.get("accion")
    alcance = cambio.get("alcance")
    if rol not in _ROLES_VALIDOS:
        raise CambioInvalidoError(f"Rol inválido: {rol!r}.")
    if rol == Rol.ADMIN.value:
        raise CambioInvalidoError("La columna Superadmin no es editable.")
    if recurso not in RECURSOS_META:
        raise CambioInvalidoError(f"Recurso inválido: {recurso!r}.")
    if accion is not None:
        if accion not in _ACCIONES_VALIDAS:
            raise CambioInvalidoError(f"Acción inválida: {accion!r}.")
        if accion == Accion.ADMIN.value:
            raise CambioInvalidoError("La acción 'admin' no es asignable desde la UI.")
        if alcance not in _ALCANCES_VALIDOS:
            raise CambioInvalidoError(f"Alcance inválido: {alcance!r} (usa own/team/linea/all).")
    return rol, recurso, accion, alcance


def aplicar_cambios(db: Session, actor, cambios: list[dict]) -> int:
    """Aplica una lista de celdas (rol,recurso → accion/alcance o None para denegar). Devuelve el
    número de celdas realmente modificadas. Transaccional + auditado. Recarga el caché al final."""
    # Validar TODO antes de tocar nada (o falla completo, sin cambios parciales).
    validados = [_validar(c) for c in cambios]
    now = datetime.now(timezone.utc)
    n = 0
    for rol, recurso, accion, alcance in validados:
        previas = db.query(RolPermiso).filter_by(rol=rol, recurso=recurso).all()
        antes = ";".join(sorted(f"{p.accion}:{p.alcance}" for p in previas)) or "—"
        nuevo = f"{accion}:{alcance}" if accion is not None else "—"
        if antes == nuevo:
            continue  # sin cambio real
        for p in previas:
            db.delete(p)
        if accion is not None:
            db.add(RolPermiso(rol=rol, recurso=recurso, accion=accion,
                              alcance=alcance, actualizado_en=now))
        registrar_evento_seguridad(
            db, actor, "PERMISO_MODIFICADO", recurso=recurso, accion=accion, alcance=alcance,
            objetivo=f"rol:{rol}", detalle=f"antes={antes} nuevo={nuevo}")
        n += 1
    db.commit()
    runtime.cargar(db)
    return n


def restablecer(db: Session, actor) -> dict:
    """Devuelve la matriz a los valores de fábrica (matrix.py). Auditado. Recarga el caché."""
    res = seed.sembrar_todo(db)  # delete-then-sync a los valores de código
    registrar_evento_seguridad(db, actor, "PERMISOS_RESTABLECIDOS", detalle=str(res))
    db.commit()
    runtime.cargar(db)
    return res


def matriz_actual(db: Session) -> list[dict]:
    """Serializa la matriz vigente (BD) al shape del GET. Fallback a fábrica si la BD está vacía."""
    filas = db.query(RolPermiso).all()
    base: dict[str, dict[str, dict]] = {}
    if filas:
        for p in filas:
            base.setdefault(p.recurso, {})[p.rol] = {"accion": p.accion, "alcance": p.alcance}
    else:
        for recurso, fila in MATRIZ.items():
            for rol, celda in fila.items():
                if celda is not None:
                    base.setdefault(recurso, {})[rol.value] = {
                        "accion": celda[0].value, "alcance": celda[1].value}

    recursos = []
    for slug in RECURSOS:  # orden estable de RECURSOS_META
        nombre, modulo = RECURSOS_META[slug]
        celdas = base.get(slug, {})
        recursos.append({
            "recurso": slug, "nombre": nombre, "modulo": modulo,
            "roles": {rol: celdas.get(rol) for rol in ROLES},
        })
    return recursos
