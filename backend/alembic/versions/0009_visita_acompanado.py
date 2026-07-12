"""visita: columna acompanado (visita acompañada por el GD)

Revision ID: 0009_visita_acompanado
Revises: 0008_indices_rendimiento
Create Date: 2026-07-12
"""
from alembic import op
import sqlalchemy as sa

revision = "0009_visita_acompanado"
down_revision = "0008_indices_rendimiento"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "FactVisita",
        sa.Column("acompanado", sa.Boolean(), nullable=False, server_default=sa.false()),
        schema="Visita",
    )
    # Quita el default a nivel de columna; el default lógico lo pone el modelo/servicio.
    op.alter_column("FactVisita", "acompanado", server_default=None, schema="Visita")


def downgrade() -> None:
    op.drop_column("FactVisita", "acompanado", schema="Visita")
