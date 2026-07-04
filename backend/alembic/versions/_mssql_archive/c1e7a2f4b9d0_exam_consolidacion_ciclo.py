"""exam.FactConsolidacionCiclo — gate de consolidación EVAL_CONOCIMIENTOS

Revision ID: c1e7a2f4b9d0
Revises: a7e2c4f9b158
Create Date: 2026-07-02
"""
from alembic import op
import sqlalchemy as sa

revision = "c1e7a2f4b9d0"
down_revision = "a7e2c4f9b158"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing = insp.get_table_names(schema="exam")
    if "FactConsolidacionCiclo" not in existing:
        op.create_table(
            "FactConsolidacionCiclo",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("ciclo_id", sa.Integer(), nullable=False),
            sa.Column("pais_codigo", sa.String(length=10), nullable=False),
            sa.Column("estado", sa.String(length=15), nullable=False, server_default="pendiente"),
            sa.Column("rms_consolidados", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("nota_promedio_equipo", sa.Numeric(5, 2), nullable=True),
            sa.Column("fecha_consolidacion", sa.DateTime(), nullable=True),
            sa.Column("consolidado_por_usuario_id", sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(["ciclo_id"], ["Config.DIM_Ciclo.id"]),
            sa.ForeignKeyConstraint(["consolidado_por_usuario_id"], ["Security.DIM_Usuario.id"]),
            sa.UniqueConstraint("ciclo_id", "pais_codigo", name="UQ_ConsolidacionCiclo_ciclo_pais"),
            schema="exam",
        )


def downgrade():
    op.drop_table("FactConsolidacionCiclo", schema="exam")
