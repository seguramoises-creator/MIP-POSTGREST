"""Motor de autorización: evalúa la matriz canónica (matrix.MATRIZ).

`user` es cualquier objeto con `.rol` (y `.rm_id`/`.gerente_id` para los filtros de scope de
`app.core.authz.scope`). El motor solo decide acción+alcance; el filtrado de datos vive en scope.py.

Reglas (spec §4.3):
- `admin` concede todas las acciones con alcance `all`.
- `configure`/`approve`/`register` conceden también `read` al mismo alcance.
- `export` es independiente de `read`; su alcance efectivo por módulo se capa por la lectura.
"""
from app.core.authz.constantes import Accion, Alcance, Recurso, alcance_min
from app.core.authz.matrix import MATRIZ

# Acciones cuya concesión implica READ al mismo alcance (export NO: es independiente)
_IMPLICAN_READ = (Accion.CONFIGURE, Accion.APPROVE, Accion.REGISTER)


def _celda(rol, recurso: str):
    return MATRIZ.get(recurso, {}).get(rol)


def can(user, accion: Accion, recurso: str):
    """Alcance (Alcance) concedido para (accion, recurso), o None si está denegado."""
    celda = _celda(user.rol, recurso)
    if celda is None:
        return None
    g_accion, g_alcance = celda
    if g_accion == Accion.ADMIN:
        return Alcance.ALL
    if g_accion == accion:
        return g_alcance
    if accion == Accion.READ and g_accion in _IMPLICAN_READ:
        return g_alcance
    return None


def puede(user, accion: Accion, recurso: str) -> bool:
    return can(user, accion, recurso) is not None


def _read_scope(user, recurso: str):
    """Alcance de READ (incluye la implicación de configure/approve/register y admin)."""
    return can(user, Accion.READ, recurso)


def alcance_export_modulo(user, recurso: str):
    """Alcance efectivo de EXPORT sobre un módulo concreto, capado por la lectura del usuario en
    ese módulo. None si el usuario no tiene capacidad de export o no lee el módulo.

    La capacidad de export vive en el recurso EXPORTACION; el tope viene de la lectura del módulo,
    de modo que exportar nunca amplía el alcance de lectura (spec §4.3)."""
    cap = can(user, Accion.EXPORT, Recurso.EXPORTACION)
    if cap is None:
        return None
    # ADMIN cae aquí con cap=ALL y lectura=ALL → min = ALL (sin caso especial).
    lectura = _read_scope(user, recurso)
    if lectura is None:
        return None
    return alcance_min(cap, lectura)
