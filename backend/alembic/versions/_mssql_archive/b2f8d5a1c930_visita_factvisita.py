"""Visita — tabla Visita.FactVisita (registro de visitas, fuente de Cobertura)

Revision ID: b2f8d5a1c930
Revises: a9d3e6b1c742
Create Date: 2026-06-30

Idempotente.
"""
from alembic import op
import sqlalchemy as sa

revision = "b2f8d5a1c930"
down_revision = "a9d3e6b1c742"
branch_labels = None
depends_on = None


def upgrade():
    insp = sa.inspect(op.get_bind())
    if not insp.has_table("FactVisita", schema="Visita"):
        op.create_table(
            "FactVisita",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("vm_id", sa.Integer(), sa.ForeignKey("Config.DIM_RM.id"), nullable=False),
            sa.Column("ciclo_id", sa.Integer(), sa.ForeignKey("Config.DIM_Ciclo.id"), nullable=False),
            sa.Column("medico_id", sa.Integer(), sa.ForeignKey("Visita.DIM_MedicoVisita.id"), nullable=False),
            sa.Column("tipo_visita", sa.CHAR(length=1), nullable=False),
            sa.Column("fecha_hora", sa.DateTime(), nullable=True),
            sa.Column("comentario", sa.String(length=1000), nullable=True),
            sa.Column("ejecutada", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("causa_no_visita", sa.String(length=80), nullable=True),
            sa.Column("registrado_por", sa.Integer(), sa.ForeignKey("Security.DIM_Usuario.id"), nullable=True),
            schema="Visita",
        )
        op.create_index("IX_FactVisita_vm_ciclo", "FactVisita", ["vm_id", "ciclo_id"], schema="Visita")
        op.create_index("IX_FactVisita_medico", "FactVisita", ["medico_id"], schema="Visita")


def downgrade():
    insp = sa.inspect(op.get_bind())
    if insp.has_table("FactVisita", schema="Visita"):
        op.drop_table("FactVisita", schema="Visita")
