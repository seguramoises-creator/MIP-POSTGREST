"""FactVisita: GPS (lat/long) + foto (BLOB) por visita

Revision ID: d4b8f1a6c290
Revises: c1e7a2f4b9d0
Create Date: 2026-07-03
"""
from alembic import op
import sqlalchemy as sa

revision = "d4b8f1a6c290"
down_revision = "c1e7a2f4b9d0"
branch_labels = None
depends_on = None

_COLS = {
    "latitud": sa.Numeric(10, 7),
    "longitud": sa.Numeric(10, 7),
    "foto": sa.LargeBinary(),
    "foto_mime": sa.String(length=40),
}


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existentes = {c["name"] for c in insp.get_columns("FactVisita", schema="Visita")}
    for nombre, tipo in _COLS.items():
        if nombre not in existentes:
            op.add_column("FactVisita", sa.Column(nombre, tipo, nullable=True), schema="Visita")


def downgrade():
    for nombre in _COLS:
        op.drop_column("FactVisita", nombre, schema="Visita")
