"""Config.DIM_Gerente: columna fecha_ingreso

Revision ID: f1c9d3b7e582
Revises: d8a2f5c1b493
Create Date: 2026-07-02

Aditiva e idempotente.
"""
from alembic import op
import sqlalchemy as sa

revision = "f1c9d3b7e582"
down_revision = "d8a2f5c1b493"
branch_labels = None
depends_on = None


def upgrade():
    insp = sa.inspect(op.get_bind())
    cols = {c["name"] for c in insp.get_columns("DIM_Gerente", schema="Config")}
    if "fecha_ingreso" not in cols:
        op.add_column("DIM_Gerente", sa.Column("fecha_ingreso", sa.Date(), nullable=True), schema="Config")


def downgrade():
    insp = sa.inspect(op.get_bind())
    cols = {c["name"] for c in insp.get_columns("DIM_Gerente", schema="Config")}
    if "fecha_ingreso" in cols:
        op.drop_column("DIM_Gerente", "fecha_ingreso", schema="Config")
