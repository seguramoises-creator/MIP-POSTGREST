"""Visita — tablas Visita.ParrillaPromocional y Visita.MuestraEntregada

Revision ID: f3b7c1d95a24
Revises: d4a1c8b6e920
Create Date: 2026-07-01

Idempotente.
"""
from alembic import op
import sqlalchemy as sa

revision = "f3b7c1d95a24"
down_revision = "d4a1c8b6e920"
branch_labels = None
depends_on = None


def upgrade():
    insp = sa.inspect(op.get_bind())
    if not insp.has_table("ParrillaPromocional", schema="Visita"):
        op.create_table(
            "ParrillaPromocional",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("ciclo_id", sa.Integer(), sa.ForeignKey("Config.DIM_Ciclo.id"), nullable=False),
            sa.Column("linea_id", sa.Integer(), sa.ForeignKey("Config.DIM_Linea.id"), nullable=False),
            sa.Column("producto", sa.String(length=120), nullable=False),
            sa.Column("mensaje_clave", sa.String(length=300), nullable=True),
            sa.Column("prioridad", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("meta_muestras", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("fecha_creacion", sa.DateTime(), nullable=True),
            sa.Column("modificado_por", sa.Integer(), sa.ForeignKey("Security.DIM_Usuario.id"), nullable=True),
            schema="Visita",
        )
        op.create_index("IX_Parrilla_ciclo_linea", "ParrillaPromocional", ["ciclo_id", "linea_id"], schema="Visita")

    if not insp.has_table("MuestraEntregada", schema="Visita"):
        op.create_table(
            "MuestraEntregada",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("vm_id", sa.Integer(), sa.ForeignKey("Config.DIM_RM.id"), nullable=False),
            sa.Column("ciclo_id", sa.Integer(), sa.ForeignKey("Config.DIM_Ciclo.id"), nullable=False),
            sa.Column("medico_id", sa.Integer(), sa.ForeignKey("Visita.DIM_MedicoVisita.id"), nullable=False),
            sa.Column("producto", sa.String(length=120), nullable=False),
            sa.Column("cantidad", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("fecha_entrega", sa.DateTime(), nullable=True),
            sa.Column("registrado_por", sa.Integer(), sa.ForeignKey("Security.DIM_Usuario.id"), nullable=True),
            schema="Visita",
        )
        op.create_index("IX_Muestra_vm_ciclo", "MuestraEntregada", ["vm_id", "ciclo_id"], schema="Visita")
        op.create_index("IX_Muestra_medico", "MuestraEntregada", ["medico_id"], schema="Visita")


def downgrade():
    insp = sa.inspect(op.get_bind())
    if insp.has_table("MuestraEntregada", schema="Visita"):
        op.drop_table("MuestraEntregada", schema="Visita")
    if insp.has_table("ParrillaPromocional", schema="Visita"):
        op.drop_table("ParrillaPromocional", schema="Visita")
