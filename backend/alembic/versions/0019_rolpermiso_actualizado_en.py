"""RBAC: FACT_RolPermiso.actualizado_en — versión del caché de la matriz editable.

La matriz de permisos pasa a ser editable desde la UI y el motor la lee de la BD (con caché).
`actualizado_en` es el sello de versión: el máximo de esta columna indica si el caché debe
recargarse. Ver docs/superpowers/specs/2026-07-18-matriz-permisos-editable-design.md.

Revision ID: 0019_rolpermiso_actualizado_en
Revises: 0018_costo_estructura_aprobacion
"""
from alembic import op
import sqlalchemy as sa

revision = "0019_rolpermiso_actualizado_en"
down_revision = "0018_costo_estructura_aprobacion"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "FACT_RolPermiso",
        sa.Column("actualizado_en", sa.DateTime(), nullable=True),
        schema="Security",
    )
    op.execute(
        'UPDATE "Security"."FACT_RolPermiso" '
        "SET actualizado_en = (now() at time zone 'utc') "
        "WHERE actualizado_en IS NULL"
    )


def downgrade():
    op.drop_column("FACT_RolPermiso", "actualizado_en", schema="Security")
