"""security: tabla FACT_PasswordReset (recuperación de contraseña por código)

Revision ID: 0010_password_reset
Revises: 0009_visita_acompanado
Create Date: 2026-07-12
"""
from alembic import op
import sqlalchemy as sa

revision = "0010_password_reset"
down_revision = "0009_visita_acompanado"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "FACT_PasswordReset",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("codigo_hash", sa.String(length=255), nullable=False),
        sa.Column("expira_en", sa.DateTime(), nullable=False),
        sa.Column("usado", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("intentos", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("creado_en", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["usuario_id"], ["Security.DIM_Usuario.id"]),
        schema="Security",
    )
    op.create_index("ix_pwdreset_usuario", "FACT_PasswordReset", ["usuario_id"], schema="Security")
    op.create_index("ix_pwdreset_expira", "FACT_PasswordReset", ["expira_en"], schema="Security")


def downgrade() -> None:
    op.drop_index("ix_pwdreset_expira", table_name="FACT_PasswordReset", schema="Security")
    op.drop_index("ix_pwdreset_usuario", table_name="FACT_PasswordReset", schema="Security")
    op.drop_table("FACT_PasswordReset", schema="Security")
