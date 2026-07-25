"""Cablear a la matriz NO debía cambiarle el acceso a nadie (jul-2026).

`dims.py`, `categorizacion.py` y `maestro_medicos.py` eran los últimos routers registrados que
seguían con `require_roles(...)` en vez de la matriz editable. Al pasarlos, el riesgo real no era
dejar un hueco abierto sino el contrario: **cerrarle la puerta en producción a un rol que hoy sí
entra** (p. ej. los usuarios CAPACITACION, que leían Categorización y el Maestro de Médicos solo
por estar autenticados).

Este test fija el contrato: para cada guard, el conjunto de roles admitidos por la matriz es
EXACTAMENTE el que admitía el `require_roles` anterior. Si alguien edita una fila de la matriz en
el código y con ello altera el acceso de estos módulos, esto lo delata.

Nota: la matriz vive en la BD y es editable desde la UI — que el cliente la cambie ahí es el
objetivo del cambio, y no afecta a este test, que valida los valores de fábrica (`matrix.MATRIZ`).
"""
from types import SimpleNamespace

import pytest

from app.models.usuario import Rol
from app.core.authz import engine, runtime
from app.core.authz.constantes import Accion, Recurso

TODOS = set(Rol)
ADMIN_GERPROD = {Rol.ADMIN, Rol.GERENTE_PRODUCTIVIDAD}
# `actualizar` del maestro era el único con RequireSupervisor (más amplio que el alta)
SUPERVISORES = ADMIN_GERPROD | {Rol.GERENTE_DISTRITO, Rol.GERENTE_MARCA}


@pytest.fixture(autouse=True)
def _matriz_de_fabrica():
    """Fuerza el fallback a `matrix.MATRIZ`: otro test pudo dejar el caché cargado."""
    runtime.invalidar()
    yield
    runtime.invalidar()


def _permitidos(accion: Accion, recurso: str) -> set:
    return {r for r in Rol if engine.can(SimpleNamespace(rol=r), accion, recurso) is not None}


@pytest.mark.parametrize("guard, esperado, accion, recurso", [
    # dims.py — antes: require_roles(ADMIN, GERENTE_PRODUCTIVIDAD) en /preview y /importar
    ("dims.ConfigDims", ADMIN_GERPROD, Accion.CONFIGURE, Recurso.ETL_CARGAR),
    # categorizacion.py — antes: get_current_active_user (cualquiera) / require_roles(ADMIN, GERPROD)
    ("categorizacion.RequireAuth", TODOS, Accion.READ, Recurso.CATEGORIZACION_OPERACION),
    ("categorizacion.RequireAdminCat", ADMIN_GERPROD, Accion.CONFIGURE, Recurso.CATEGORIZACION_OPERACION),
    # maestro_medicos.py — antes: Lectura=cualquiera, Escritura=ADMIN+GERPROD, Supervisor=+GD+MARCA
    ("maestro.RequireLectura", TODOS, Accion.READ, Recurso.MEDICO_MAESTRO),
    ("maestro.RequireEscritura", ADMIN_GERPROD, Accion.CONFIGURE, Recurso.MEDICO_MAESTRO),
    ("maestro.RequireSupervisor", SUPERVISORES, Accion.CONFIGURE, Recurso.MEDICO_MAESTRO_EDITAR),
])
def test_el_guard_admite_exactamente_los_mismos_roles_que_antes(guard, esperado, accion, recurso):
    actual = _permitidos(accion, recurso)
    assert actual == esperado, (
        f"{guard}: pierden acceso {sorted(r.value for r in esperado - actual)}; "
        f"ganan {sorted(r.value for r in actual - esperado)}"
    )


def test_capacitacion_conserva_la_lectura_que_ya_tenia():
    """Los 4 usuarios CAPACITACION reales leían ambos módulos por estar autenticados."""
    cap = SimpleNamespace(rol=Rol.CAPACITACION)
    assert engine.can(cap, Accion.READ, Recurso.CATEGORIZACION_OPERACION) is not None
    assert engine.can(cap, Accion.READ, Recurso.MEDICO_MAESTRO) is not None
    # ...pero sigue sin poder configurar nada de estos módulos, como hasta ahora.
    assert engine.can(cap, Accion.CONFIGURE, Recurso.CATEGORIZACION_OPERACION) is None
    assert engine.can(cap, Accion.CONFIGURE, Recurso.MEDICO_MAESTRO) is None
    assert engine.can(cap, Accion.CONFIGURE, Recurso.MEDICO_MAESTRO_EDITAR) is None


def test_los_recursos_del_spec_no_se_tocaron():
    """`categorizacion.detalle` y `medico.panel` los consumen `admin.py` y `visita.py`: se crearon
    recursos nuevos justamente para no alterarlos. GERENTE_PRODUCTIVIDAD sigue fuera de ambos."""
    prod = SimpleNamespace(rol=Rol.GERENTE_PRODUCTIVIDAD)
    assert engine.can(prod, Accion.READ, Recurso.CATEGORIZACION_DETALLE) is None
    assert engine.can(prod, Accion.READ, Recurso.MEDICO_PANEL) is None
