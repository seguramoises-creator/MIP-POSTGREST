"""Visita — CostoEstructura y CostoProducto (modelo financiero Costo & ROI)

Revision ID: a7e2c4f9b158
Revises: f1c9d3b7e582
Create Date: 2026-07-02

Idempotente.
"""
from alembic import op
import sqlalchemy as sa

revision = "a7e2c4f9b158"
down_revision = "f1c9d3b7e582"
branch_labels = None
depends_on = None


def upgrade():
    insp = sa.inspect(op.get_bind())
    if not insp.has_table("CostoEstructura", schema="Visita"):
        op.create_table(
            "CostoEstructura",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("ciclo_id", sa.Integer(), sa.ForeignKey("Config.DIM_Ciclo.id"), nullable=False),
            sa.Column("linea_id", sa.Integer(), sa.ForeignKey("Config.DIM_Linea.id"), nullable=True),
            sa.Column("moneda", sa.String(8), nullable=False, server_default="RD$"),
            sa.Column("salario_mensual", sa.Numeric(14, 2), nullable=False, server_default="0"),
            sa.Column("cargas_pct", sa.Numeric(6, 2), nullable=False, server_default="0"),
            sa.Column("viaticos_dia", sa.Numeric(12, 2), nullable=False, server_default="0"),
            sa.Column("materiales_ciclo", sa.Numeric(12, 2), nullable=False, server_default="0"),
            sa.Column("dias_campo", sa.Integer(), nullable=False, server_default="19"),
            sa.Column("total_visitas", sa.Integer(), nullable=False, server_default="190"),
            sa.Column("dias_mes", sa.Integer(), nullable=False, server_default="21"),
            sa.Column("visitadores", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("visitas_ciclo_vm", sa.Integer(), nullable=False, server_default="190"),
            sa.Column("ciclos_anio", sa.Integer(), nullable=False, server_default="11"),
            sa.Column("coef_conservador", sa.Numeric(5, 2), nullable=False, server_default="0.40"),
            sa.Column("coef_optimista", sa.Numeric(5, 2), nullable=False, server_default="0.70"),
            sa.Column("psp_a", sa.Numeric(14, 2), nullable=False, server_default="0"),
            sa.Column("psp_b", sa.Numeric(14, 2), nullable=False, server_default="0"),
            sa.Column("psp_c", sa.Numeric(14, 2), nullable=False, server_default="0"),
            sa.Column("med_sin_visitar_a", sa.Integer(), nullable=True),
            sa.Column("med_sin_visitar_b", sa.Integer(), nullable=True),
            sa.Column("med_sin_visitar_c", sa.Integer(), nullable=True),
            sa.Column("fecha_actualizacion", sa.DateTime(), nullable=True),
            sa.Column("modificado_por", sa.Integer(), sa.ForeignKey("Security.DIM_Usuario.id"), nullable=True),
            schema="Visita",
        )
        op.create_index("IX_CostoEstructura_ciclo_linea", "CostoEstructura", ["ciclo_id", "linea_id"], schema="Visita")

    if not insp.has_table("CostoProducto", schema="Visita"):
        op.create_table(
            "CostoProducto",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("ciclo_id", sa.Integer(), sa.ForeignKey("Config.DIM_Ciclo.id"), nullable=False),
            sa.Column("linea_id", sa.Integer(), sa.ForeignKey("Config.DIM_Linea.id"), nullable=True),
            sa.Column("producto_id", sa.Integer(), sa.ForeignKey("Config.DIM_Producto.id"), nullable=True),
            sa.Column("producto", sa.String(120), nullable=False),
            sa.Column("orden", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("costo_unitario_muestra", sa.Numeric(12, 2), nullable=False, server_default="0"),
            sa.Column("cantidad_muestras", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("pool_ventas", sa.Numeric(16, 2), nullable=False, server_default="0"),
            sa.Column("visitas_detalladas", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("presupuesto_anual", sa.Numeric(16, 2), nullable=False, server_default="0"),
            sa.Column("precio_prom", sa.Numeric(12, 2), nullable=False, server_default="0"),
            schema="Visita",
        )
        op.create_index("IX_CostoProducto_ciclo_linea", "CostoProducto", ["ciclo_id", "linea_id"], schema="Visita")


def downgrade():
    insp = sa.inspect(op.get_bind())
    if insp.has_table("CostoProducto", schema="Visita"):
        op.drop_table("CostoProducto", schema="Visita")
    if insp.has_table("CostoEstructura", schema="Visita"):
        op.drop_table("CostoEstructura", schema="Visita")
