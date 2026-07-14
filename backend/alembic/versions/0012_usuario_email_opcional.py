"""DIM_Usuario.email OPCIONAL (nullable) — permite usuarios sin correo

Revision ID: 0012_usuario_email_opcional
Revises: 0011_rm_coaching_min_dia
Create Date: 2026-07-13
"""
from alembic import op
import sqlalchemy as sa

revision = "0012_usuario_email_opcional"
down_revision = "0011_rm_coaching_min_dia"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # El índice único se conserva; en Postgres admite múltiples NULL.
    op.alter_column("DIM_Usuario", "email",
                    existing_type=sa.String(200), nullable=True, schema="Security")


def downgrade() -> None:
    op.alter_column("DIM_Usuario", "email",
                    existing_type=sa.String(200), nullable=False, schema="Security")
