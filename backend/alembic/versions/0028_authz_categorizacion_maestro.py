"""Siembra los 3 recursos RBAC de Categorización y Maestro de Médicos.

`categorizacion.py` y `maestro_medicos.py` pasaron de `require_roles(...)` a la matriz editable.
Sus 3 recursos nuevos DEBEN existir en `Security.*` ANTES de que el código que los exige empiece
a atender peticiones, por cómo funciona el runtime (`app/core/authz/runtime.celda`): una vez que
el caché se cargó desde una BD ya sembrada, **un recurso ausente se deniega a todos** — no cae a
los valores de fábrica de `matrix.py`. Sin esta migración, Categorización y el Maestro de Médicos
responderían 403 a todo el mundo, ADMIN incluido, hasta correr `scripts/seed_authz.py` a mano.

Va como migración justamente porque las migraciones SÍ corren solas al arrancar el contenedor
(`RUN_MIGRATIONS=1`), mientras que el seed no. Y se insertan solo estas filas, en vez de invocar
`seed.sembrar_todo`, porque ese seed sincroniza en ambos sentidos: **borraría las ediciones que el
cliente haya hecho** desde Administración → Roles y Permisos.

Las filas reproducen exactamente el acceso que ambos routers ya concedían con `require_roles`
(contrato fijado en `tests/test_authz_wiring_calcado.py`): nadie gana ni pierde permisos aquí.
Idempotente: `WHERE NOT EXISTS` deja intacto lo ya sembrado o editado.

Revision ID: 0028_authz_categorizacion_maestro
Revises: 0027_snapshot_loadbatchkey_not_null
"""
import sqlalchemy as sa
from alembic import op

revision = "0028_authz_categorizacion_maestro"
down_revision = "0027_snapshot_loadbatchkey_not_null"
branch_labels = None
depends_on = None

_RECURSOS = [
    ("categorizacion.operacion", "Categorización: pantallas operativas y parámetros", "Panel médico"),
    ("medico.maestro", "Maestro de médicos: consulta e importación", "Panel médico"),
    ("medico.maestro.editar", "Maestro de médicos: editar ficha existente", "Panel médico"),
]

# (rol, recurso, accion, alcance) — calcado de matrix.MATRIZ al 25-jul-2026
_PERMISOS = [
    ("REPRESENTANTE_MEDICO", "categorizacion.operacion", "read", "own"),
    ("GERENTE_DISTRITO", "categorizacion.operacion", "read", "team"),
    ("GERENTE_MARCA", "categorizacion.operacion", "read", "all"),
    ("GERENTE_MARKETING", "categorizacion.operacion", "read", "all"),
    ("GERENTE_PRODUCTIVIDAD", "categorizacion.operacion", "configure", "all"),
    ("GERENTE_MEDICO", "categorizacion.operacion", "read", "all"),
    ("PRESIDENCIA", "categorizacion.operacion", "read", "all"),
    ("ANALISTA_DATOS", "categorizacion.operacion", "read", "all"),
    ("FINANZAS", "categorizacion.operacion", "read", "all"),
    ("ADMIN", "categorizacion.operacion", "admin", "all"),
    ("CAPACITACION", "categorizacion.operacion", "read", "all"),
    ("DIR_COMERCIAL", "categorizacion.operacion", "read", "all"),
    ("CONSULTA", "categorizacion.operacion", "read", "all"),
    ("REPRESENTANTE_MEDICO", "medico.maestro", "read", "all"),
    ("GERENTE_DISTRITO", "medico.maestro", "read", "all"),
    ("GERENTE_MARCA", "medico.maestro", "read", "all"),
    ("GERENTE_MARKETING", "medico.maestro", "read", "all"),
    ("GERENTE_PRODUCTIVIDAD", "medico.maestro", "configure", "all"),
    ("GERENTE_MEDICO", "medico.maestro", "read", "all"),
    ("PRESIDENCIA", "medico.maestro", "read", "all"),
    ("ANALISTA_DATOS", "medico.maestro", "read", "all"),
    ("FINANZAS", "medico.maestro", "read", "all"),
    ("ADMIN", "medico.maestro", "admin", "all"),
    ("CAPACITACION", "medico.maestro", "read", "all"),
    ("DIR_COMERCIAL", "medico.maestro", "read", "all"),
    ("CONSULTA", "medico.maestro", "read", "all"),
    ("GERENTE_DISTRITO", "medico.maestro.editar", "configure", "all"),
    ("GERENTE_MARCA", "medico.maestro.editar", "configure", "all"),
    ("GERENTE_PRODUCTIVIDAD", "medico.maestro.editar", "configure", "all"),
    ("ADMIN", "medico.maestro.editar", "admin", "all"),
]

_SLUGS = tuple(s for s, _, _ in _RECURSOS)


_INS_RECURSO = sa.text(
    'INSERT INTO "Security"."DIM_Recurso" ("slug", "nombre", "modulo") '
    'SELECT :slug, :nombre, :modulo WHERE NOT EXISTS '
    '(SELECT 1 FROM "Security"."DIM_Recurso" WHERE "slug" = :slug)'
)
# La clave natural es (rol, recurso, accion): si el cliente ya editó el ALCANCE de una celda
# desde la UI, esta migración la respeta y no la pisa.
_INS_PERMISO = sa.text(
    'INSERT INTO "Security"."FACT_RolPermiso" ("rol", "recurso", "accion", "alcance") '
    'SELECT :rol, :recurso, :accion, :alcance WHERE NOT EXISTS '
    '(SELECT 1 FROM "Security"."FACT_RolPermiso" '
    ' WHERE "rol" = :rol AND "recurso" = :recurso AND "accion" = :accion)'
)


def upgrade() -> None:
    conn = op.get_bind()
    for slug, nombre, modulo in _RECURSOS:
        conn.execute(_INS_RECURSO, {"slug": slug, "nombre": nombre, "modulo": modulo})
    for rol, recurso, accion, alcance in _PERMISOS:
        conn.execute(_INS_PERMISO,
                     {"rol": rol, "recurso": recurso, "accion": accion, "alcance": alcance})


def downgrade() -> None:
    conn = op.get_bind()
    for slug in _SLUGS:
        conn.execute(sa.text('DELETE FROM "Security"."FACT_RolPermiso" WHERE "recurso" = :s'),
                     {"s": slug})
        conn.execute(sa.text('DELETE FROM "Security"."DIM_Recurso" WHERE "slug" = :s'), {"s": slug})
