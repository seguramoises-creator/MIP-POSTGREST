"""DIM_Usuario.email OPCIONAL (nullable) — permite usuarios sin correo

Revision ID: 0014_usuario_email_opcional
Revises: 0013_medicovisita_maestro_fk
Create Date: 2026-07-13
"""
from alembic import op
import sqlalchemy as sa

revision = "0014_usuario_email_opcional"
down_revision = "0013_medicovisita_maestro_fk"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # El índice único se conserva; en Postgres admite múltiples NULL.
    op.alter_column("DIM_Usuario", "email",
                    existing_type=sa.String(200), nullable=True, schema="Security")


def downgrade() -> None:
    op.alter_column("DIM_Usuario", "email",
                    existing_type=sa.String(200), nullable=False, schema="Security")
