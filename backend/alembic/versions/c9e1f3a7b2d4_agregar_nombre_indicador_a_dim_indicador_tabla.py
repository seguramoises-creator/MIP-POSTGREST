"""Agregar nombre_indicador a Config.DIM_IndicadorTabla

Revision ID: c9e1f3a7b2d4
Revises: b8c4d2e1f5a9
Create Date: 2026-06-12
"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = 'c9e1f3a7b2d4'
down_revision: Union[str, Sequence[str], None] = 'b8c4d2e1f5a9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'DIM_IndicadorTabla',
        sa.Column('nombre_indicador', sa.String(100), nullable=True),
        schema='Config',
    )


def downgrade() -> None:
    op.drop_column('DIM_IndicadorTabla', 'nombre_indicador', schema='Config')
