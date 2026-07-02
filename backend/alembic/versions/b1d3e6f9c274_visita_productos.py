"""Visita — FactVisita: columna productos (productos detallados en la visita)

Revision ID: b1d3e6f9c274
Revises: e9f4b2c7a831
Create Date: 2026-07-01

Aditiva e idempotente.
"""
from alembic import op
import sqlalchemy as sa

revision = "b1d3e6f9c274"
down_revision = "e9f4b2c7a831"
branch_labels = None
depends_on = None


def upgrade():
    insp = sa.inspect(op.get_bind())
    cols = {c["name"] for c in insp.get_columns("FactVisita", schema="Visita")}
    if "productos" not in cols:
        op.add_column("FactVisita", sa.Column("productos", sa.String(length=300), nullable=True), schema="Visita")


def downgrade():
    insp = sa.inspect(op.get_bind())
    cols = {c["name"] for c in insp.get_columns("FactVisita", schema="Visita")}
    if "productos" in cols:
        op.drop_column("FactVisita", "productos", schema="Visita")
