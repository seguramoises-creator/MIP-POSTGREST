"""Visita — tabla Visita.PlaneacionCiclo (planeación del ciclo)

Revision ID: c5e9a2f7d418
Revises: b2f8d5a1c930
Create Date: 2026-06-30

Idempotente.
"""
from alembic import op
import sqlalchemy as sa

revision = "c5e9a2f7d418"
down_revision = "b2f8d5a1c930"
branch_labels = None
depends_on = None


def upgrade():
    insp = sa.inspect(op.get_bind())
    if not insp.has_table("PlaneacionCiclo", schema="Visita"):
        op.create_table(
            "PlaneacionCiclo",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("vm_id", sa.Integer(), sa.ForeignKey("Config.DIM_RM.id"), nullable=False),
            sa.Column("ciclo_id", sa.Integer(), sa.ForeignKey("Config.DIM_Ciclo.id"), nullable=False),
            sa.Column("medico_id", sa.Integer(), sa.ForeignKey("Visita.DIM_MedicoVisita.id"), nullable=False),
            sa.Column("tipo_visita", sa.CHAR(length=1), nullable=False),
            sa.Column("semana", sa.Integer(), nullable=False),
            sa.Column("dia_semana", sa.String(length=12), nullable=True),
            sa.Column("hora_estimada", sa.String(length=5), nullable=True),
            sa.Column("fecha_creacion", sa.DateTime(), nullable=True),
            sa.Column("modificado_por", sa.Integer(), sa.ForeignKey("Security.DIM_Usuario.id"), nullable=True),
            schema="Visita",
        )
        op.create_index("IX_Planeacion_vm_ciclo", "PlaneacionCiclo", ["vm_id", "ciclo_id"], schema="Visita")


def downgrade():
    insp = sa.inspect(op.get_bind())
    if insp.has_table("PlaneacionCiclo", schema="Visita"):
        op.drop_table("PlaneacionCiclo", schema="Visita")
