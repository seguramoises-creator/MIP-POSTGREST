"""Siembra el recurso RBAC `planeacion.aprobar` (el GD aprueba la planeación de su equipo).

Mismo motivo que la `0028`: una vez cargado el caché de permisos desde una BD ya sembrada,
**un recurso ausente se deniega a todos** (`runtime.celda` no cae a `matrix.py`). Sin esta
migración, los endpoints de aprobar/devolver responderían 403 incluso al ADMIN.

Se insertan solo estas filas —nunca `seed.sembrar_todo`, que sincroniza en ambos sentidos y
borraría las ediciones que el cliente haya hecho desde Administración → Roles y Permisos.
Idempotente: `WHERE NOT EXISTS` deja intacto lo ya sembrado o editado.

Revision ID: 0039_authz_planeacion_aprobar
Revises: 0038_uuid_cliente_visitas
"""
import sqlalchemy as sa
from alembic import op

revision = "0039_authz_planeacion_aprobar"
down_revision = "0038_uuid_cliente_visitas"
branch_labels = None
depends_on = None

_SLUG = "planeacion.aprobar"
_PERMISOS = [
    ("GERENTE_DISTRITO", "approve", "team"),
    ("ADMIN", "admin", "all"),
]


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text(
        'INSERT INTO "Security"."DIM_Recurso" ("slug", "nombre", "modulo") '
        'SELECT :slug, :nombre, :modulo WHERE NOT EXISTS '
        '(SELECT 1 FROM "Security"."DIM_Recurso" WHERE "slug" = :slug)'),
        {"slug": _SLUG, "nombre": "Aprobación de la planeación del ciclo (VM→GD)",
         "modulo": "Planeación y cobertura"})
    for rol, accion, alcance in _PERMISOS:
        conn.execute(sa.text(
            'INSERT INTO "Security"."FACT_RolPermiso" ("rol", "recurso", "accion", "alcance") '
            'SELECT :rol, :recurso, :accion, :alcance WHERE NOT EXISTS '
            '(SELECT 1 FROM "Security"."FACT_RolPermiso" '
            ' WHERE "rol" = :rol AND "recurso" = :recurso AND "accion" = :accion)'),
            {"rol": rol, "recurso": _SLUG, "accion": accion, "alcance": alcance})


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text('DELETE FROM "Security"."FACT_RolPermiso" WHERE "recurso" = :s'), {"s": _SLUG})
    conn.execute(sa.text('DELETE FROM "Security"."DIM_Recurso" WHERE "slug" = :s'), {"s": _SLUG})
