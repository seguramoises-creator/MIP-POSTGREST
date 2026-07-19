"""Runtime de la matriz RBAC: caché en memoria alimentado desde la BD (fuente de verdad).

`engine.can()` lee de aquí (vía `celda`). La matriz es editable desde la UI: cuando cambia, el
sello `MAX(FACT_RolPermiso.actualizado_en)` avanza y cada worker recarga en su próxima petición.

Salvaguarda anti-bloqueo: si el caché aún NO se cargó (arranque, BD vacía o inaccesible), `celda`
cae a los valores de fábrica de `matrix.MATRIZ`. Una vez cargado desde una BD sembrada, la BD manda
(la ausencia de fila = celda denegada, no fallback).
"""
from threading import Lock

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.authz.constantes import Accion, Alcance
from app.core.authz.matrix import MATRIZ
from app.models.seguridad_rbac import RolPermiso

_CACHE: dict[str, dict[str, tuple]] = {}  # {recurso: {rol_str: (Accion, Alcance)}}
_version = None                           # MAX(actualizado_en) de la última carga
_cargado = False
_lock = Lock()


def _leer_version(db: Session):
    return db.query(func.max(RolPermiso.actualizado_en)).scalar()


def cargar(db: Session) -> None:
    """Reconstruye el caché desde FACT_RolPermiso y fija la versión."""
    global _CACHE, _version, _cargado
    nuevo: dict[str, dict[str, tuple]] = {}
    for p in db.query(RolPermiso).all():
        try:
            celda = (Accion(p.accion), Alcance(p.alcance))
        except ValueError:
            continue  # fila con valor fuera del enum → se ignora
        nuevo.setdefault(p.recurso, {})[p.rol] = celda
    with _lock:
        _CACHE = nuevo
        _version = _leer_version(db)
        _cargado = True


def refrescar_si_cambio(db: Session) -> None:
    """Recarga el caché solo si la versión de la BD cambió. Barato (1 query MAX). Nunca lanza:
    ante cualquier fallo (columna aún sin migrar, BD caída) deja el caché como está."""
    try:
        v = _leer_version(db)
    except Exception:  # noqa: BLE001
        return
    if not _cargado or v != _version:
        try:
            cargar(db)
        except Exception:  # noqa: BLE001
            pass


def celda(rol, recurso: str):
    """Celda base (Accion, Alcance) para (rol, recurso), o None si está denegada.
    Fallback a fábrica (matrix.MATRIZ) si el caché no se cargó O si la BD está vacía (anti-bloqueo:
    una tabla de permisos vacía nunca deja a todos sin acceso — se usan los valores de fábrica)."""
    if not _cargado or not _CACHE:
        return MATRIZ.get(recurso, {}).get(rol)
    return _CACHE.get(recurso, {}).get(getattr(rol, "value", rol))


def invalidar() -> None:
    """Fuerza el fallback a fábrica hasta la próxima carga (útil en pruebas)."""
    global _cargado
    _cargado = False
