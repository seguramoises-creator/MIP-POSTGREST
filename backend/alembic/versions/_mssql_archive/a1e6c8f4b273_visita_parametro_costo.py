"""Visita — tabla Visita.ParametroCosto (Costo & ROI)

Revision ID: a1e6c8f4b273
Revises: f3b7c1d95a24
Create Date: 2026-07-01

Idempotente.
"""
from alembic import op
import sqlalchemy as sa

revision = "a1e6c8f4b273"
down_revision = "f3b7c1d95a24"
branch_labels = None
depends_on = None


def upgrade():
    insp = sa.inspect(op.get_bind())
    if not insp.has_table("ParametroCosto", schema="Visita"):
        op.create_table(
            "ParametroCosto",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("ciclo_id", sa.Integer(), sa.ForeignKey("Config.DIM_Ciclo.id"), nullable=False),
            sa.Column("linea_id", sa.Integer(), sa.ForeignKey("Config.DIM_Linea.id"), nullable=True),
            sa.Column("costo_visita", sa.Numeric(14, 2), nullable=False, server_default="0"),
            sa.Column("costo_muestra", sa.Numeric(14, 2), nullable=False, server_default="0"),
            sa.Column("costo_fijo_ciclo", sa.Numeric(14, 2), nullable=False, server_default="0"),
            sa.Column("moneda", sa.String(length=8), nullable=False, server_default="RD$"),
            sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("fecha_actualizacion", sa.DateTime(), nullable=True),
            sa.Column("modificado_por", sa.Integer(), sa.ForeignKey("Security.DIM_Usuario.id"), nullable=True),
            schema="Visita",
        )
        op.create_index("IX_ParamCosto_ciclo_linea", "ParametroCosto", ["ciclo_id", "linea_id"], schema="Visita")


def downgrade():
    insp = sa.inspect(op.get_bind())
    if insp.has_table("ParametroCosto", schema="Visita"):
        op.drop_table("ParametroCosto", schema="Visita")
