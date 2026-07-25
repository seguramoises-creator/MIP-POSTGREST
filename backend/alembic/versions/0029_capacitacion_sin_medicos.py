"""Retira a CAPACITACION la lectura de Categorización y del Maestro de Médicos.

La migración 0028 le concedió esa lectura a propósito: cuando `categorizacion.py` y
`maestro_medicos.py` usaban `require_roles`, leerlos solo exigía estar autenticado, así que
CAPACITACION ya lo hacía, y el criterio al cablearlos fue no quitarle acceso a nadie.

Al verlo en pantalla el cliente lo rechazó: como la navegación pasó a gobernarse con esos mismos
recursos, al rol le apareció el módulo "Médicos" (pestañas Categorización + Maestro) en el menú
lateral, que no le corresponde. CAPACITACION coordina exámenes y nada más — que era lo que decía
el diseño original de su fila en la matriz.

Negar el recurso quita el ítem del menú y bloquea la API a la vez, porque el frontend deriva la
navegación de `/authz/me/permisos`. No se toca `examen.*`: su función central queda intacta.

Idempotente: si el permiso ya se retiró desde Administración → Roles y Permisos, no borra nada.

Revision ID: 0029_capacitacion_sin_medicos
Revises: 0028_authz_categ_maestro
"""
import sqlalchemy as sa
from alembic import op

revision = "0029_capacitacion_sin_medicos"
down_revision = "0028_authz_categ_maestro"
branch_labels = None
depends_on = None

_RECURSOS = ("categorizacion.operacion", "medico.maestro")

_DEL = sa.text(
    'DELETE FROM "Security"."FACT_RolPermiso" '
    'WHERE "rol" = \'CAPACITACION\' AND "recurso" = :r'
)
_INS = sa.text(
    'INSERT INTO "Security"."FACT_RolPermiso" ("rol", "recurso", "accion", "alcance") '
    "SELECT 'CAPACITACION', :r, 'read', 'all' WHERE NOT EXISTS "
    '(SELECT 1 FROM "Security"."FACT_RolPermiso" '
    ' WHERE "rol" = \'CAPACITACION\' AND "recurso" = :r AND "accion" = \'read\')'
)


def upgrade() -> None:
    conn = op.get_bind()
    for recurso in _RECURSOS:
        conn.execute(_DEL, {"r": recurso})


def downgrade() -> None:
    conn = op.get_bind()
    for recurso in _RECURSOS:
        conn.execute(_INS, {"r": recurso})
