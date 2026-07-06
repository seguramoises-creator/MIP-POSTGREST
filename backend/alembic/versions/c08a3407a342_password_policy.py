"""password policy

Revision ID: c08a3407a342
Revises: 0003_widen_periodo
Create Date: 2026-07-06 16:38:54.491496

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c08a3407a342'
down_revision: Union[str, Sequence[str], None] = '0003_widen_periodo'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('DIM_Usuario',
        sa.Column('password_actualizado_en', sa.DateTime(), nullable=True),
        schema='Security')
    # Backfill: el reloj de expiracion arranca AL MIGRAR (no en created_at),
    # para no forzar cambios sorpresa tras el deploy.
    op.execute('UPDATE "Security"."DIM_Usuario" '
               "SET password_actualizado_en = (now() at time zone 'utc') "
               "WHERE password_actualizado_en IS NULL")
    op.create_table('FACT_PasswordHistorial',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('usuario_id', sa.Integer(), nullable=False),
        sa.Column('hashed_password', sa.String(length=255), nullable=False),
        sa.Column('creado_en', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['usuario_id'], ['Security.DIM_Usuario.id']),
        sa.PrimaryKeyConstraint('id'),
        schema='Security')
    op.create_index('ix_Security_FACT_PasswordHistorial_usuario_id',
                    'FACT_PasswordHistorial', ['usuario_id'], schema='Security')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_Security_FACT_PasswordHistorial_usuario_id',
                  table_name='FACT_PasswordHistorial', schema='Security')
    op.drop_table('FACT_PasswordHistorial', schema='Security')
    op.drop_column('DIM_Usuario', 'password_actualizado_en', schema='Security')
