"""RBAC Fase 2 — workflow de aprobación de Costo/ROI (Visita.CostoEstructura).

Finanzas configura (estado BORRADOR) → Director aprueba (estado APROBADO). Un APROBADO no se
edita salvo reapertura por ADMIN (excepción de dato cerrado, auditada). Aditivo: las filas
existentes quedan en BORRADOR.

Revision ID: 0018_costo_estructura_aprobacion
Revises: 0017_rbac_fase1
Create Date: 2026-07-18
"""
from alembic import op
import sqlalchemy as sa

revision = "0018_costo_estructura_aprobacion"
down_revision = "0017_rbac_fase1"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("CostoEstructura",
                  sa.Column("estado", sa.String(12), nullable=False, server_default="BORRADOR"),
                  schema="Visita")
    op.add_column("CostoEstructura",
                  sa.Column("aprobado_por", sa.Integer(), nullable=True),
                  schema="Visita")
    op.add_column("CostoEstructura",
                  sa.Column("aprobado_en", sa.DateTime(), nullable=True),
                  schema="Visita")
    op.create_foreign_key(
        "FK_CostoEstructura_aprobado_por", "CostoEstructura", "DIM_Usuario",
        ["aprobado_por"], ["id"], source_schema="Visita", referent_schema="Security")


def downgrade():
    op.drop_constraint("FK_CostoEstructura_aprobado_por", "CostoEstructura",
                       schema="Visita", type_="foreignkey")
    op.drop_column("CostoEstructura", "aprobado_en", schema="Visita")
    op.drop_column("CostoEstructura", "aprobado_por", schema="Visita")
    op.drop_column("CostoEstructura", "estado", schema="Visita")
