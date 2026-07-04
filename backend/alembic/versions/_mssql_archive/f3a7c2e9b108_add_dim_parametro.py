"""add Config.DIM_Parametro (parámetros de sistema clave-valor en runtime)

Revision ID: f3a7c2e9b108
Revises: d4b8c1f6a920
Create Date: 2026-06-29

Tabla clave-valor para parámetros editables sin reiniciar (ej. EXAMEN_IA_DEMO).
Idempotente: no falla si la tabla ya existe.
"""
from alembic import op
import sqlalchemy as sa

revision = "f3a7c2e9b108"
down_revision = "d4b8c1f6a920"
branch_labels = None
depends_on = None


def upgrade():
    insp = sa.inspect(op.get_bind())
    existe = insp.has_table("DIM_Parametro", schema="Config")
    if not existe:
        op.create_table(
            "DIM_Parametro",
            sa.Column("clave", sa.String(length=80), primary_key=True, nullable=False),
            sa.Column("valor", sa.String(length=400), nullable=False),
            sa.Column("actualizado", sa.DateTime(), nullable=True),
            schema="Config",
        )


def downgrade():
    insp = sa.inspect(op.get_bind())
    if insp.has_table("DIM_Parametro", schema="Config"):
        op.drop_table("DIM_Parametro", schema="Config")
