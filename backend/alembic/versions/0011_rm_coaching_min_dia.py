"""DIM_RM: columna coaching_min_dia (mínimo de visitas acompañadas/día para hoja MORE)

Revision ID: 0011_rm_coaching_min_dia
Revises: 0010_password_reset
Create Date: 2026-07-13
"""
from alembic import op
import sqlalchemy as sa

revision = "0011_rm_coaching_min_dia"
down_revision = "0010_password_reset"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "DIM_RM",
        sa.Column("coaching_min_dia", sa.Integer(), nullable=False, server_default="5"),
        schema="Config",
    )


def downgrade() -> None:
    op.drop_column("DIM_RM", "coaching_min_dia", schema="Config")
