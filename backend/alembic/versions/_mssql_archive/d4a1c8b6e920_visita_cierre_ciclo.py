"""Visita — tabla Visita.CierreCicloVisita (cierre de ciclo / ruptura de secuencia)

Revision ID: d4a1c8b6e920
Revises: c5e9a2f7d418
Create Date: 2026-07-01

Idempotente.
"""
from alembic import op
import sqlalchemy as sa

revision = "d4a1c8b6e920"
down_revision = "c5e9a2f7d418"
branch_labels = None
depends_on = None


def upgrade():
    insp = sa.inspect(op.get_bind())
    if not insp.has_table("CierreCicloVisita", schema="Visita"):
        op.create_table(
            "CierreCicloVisita",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("ciclo_id", sa.Integer(), sa.ForeignKey("Config.DIM_Ciclo.id"), nullable=False),
            sa.Column("fecha_cierre", sa.DateTime(), nullable=True),
            sa.Column("panel", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("visitados", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("sin_visitar", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("ruptura_nueva", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("ruptura_critica", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("cerrado_por", sa.Integer(), sa.ForeignKey("Security.DIM_Usuario.id"), nullable=True),
            schema="Visita",
        )
        op.create_index("IX_CierreVisita_ciclo", "CierreCicloVisita", ["ciclo_id"], schema="Visita")


def downgrade():
    insp = sa.inspect(op.get_bind())
    if insp.has_table("CierreCicloVisita", schema="Visita"):
        op.drop_table("CierreCicloVisita", schema="Visita")
