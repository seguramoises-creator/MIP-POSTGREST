"""Activación de cuenta por enlace de un solo uso.

Sustituye el envío de contraseñas temporales por correo. Crea:
- `Security.FACT_ActivacionCuenta` — tokens de activación (hash SHA-256, un solo uso, caducan).
- `Security.DIM_Usuario.activado_en` — cuándo el dueño de la cuenta fijó su propia clave.

Backfill: a los usuarios YA existentes se les pone `activado_en = created_at`. Todos tienen
contraseña funcionando, así que darlos por activados es lo correcto — dejarlos en NULL los
bloquearía a todos en el próximo despliegue.

Revision ID: 0023_activacion_cuenta
Revises: 0022_medico_solicitud_cambio
"""
from alembic import op
import sqlalchemy as sa

revision = "0023_activacion_cuenta"
down_revision = "0022_medico_solicitud_cambio"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("DIM_Usuario", sa.Column("activado_en", sa.DateTime(), nullable=True),
                  schema="Security")
    # Los usuarios que ya existían quedan activados: su contraseña ya funciona.
    op.execute('UPDATE "Security"."DIM_Usuario" '
               'SET activado_en = COALESCE(created_at, NOW()) WHERE activado_en IS NULL')

    op.create_table(
        "FACT_ActivacionCuenta",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expira_en", sa.DateTime(), nullable=False),
        sa.Column("usado", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("usado_en", sa.DateTime(), nullable=True),
        sa.Column("usado_ip", sa.String(length=50), nullable=True),
        sa.Column("creado_en", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["usuario_id"], ["Security.DIM_Usuario.id"]),
        sa.PrimaryKeyConstraint("id"),
        schema="Security",
    )
    op.create_index("ix_activacion_usuario", "FACT_ActivacionCuenta", ["usuario_id"],
                    schema="Security")
    op.create_index("ix_activacion_token", "FACT_ActivacionCuenta", ["token_hash"],
                    unique=True, schema="Security")
    op.create_index("ix_activacion_expira", "FACT_ActivacionCuenta", ["expira_en"],
                    schema="Security")


def downgrade():
    op.drop_index("ix_activacion_expira", "FACT_ActivacionCuenta", schema="Security")
    op.drop_index("ix_activacion_token", "FACT_ActivacionCuenta", schema="Security")
    op.drop_index("ix_activacion_usuario", "FACT_ActivacionCuenta", schema="Security")
    op.drop_table("FACT_ActivacionCuenta", schema="Security")
    op.drop_column("DIM_Usuario", "activado_en", schema="Security")
