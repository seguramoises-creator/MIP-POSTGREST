"""Agregar codigo_indicador y corregir nombre_indicador en DIM_IndicadorTabla

Revision ID: d1f4a8c3e9b2
Revises: c9e1f3a7b2d4
Create Date: 2026-06-12
"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = 'd1f4a8c3e9b2'
down_revision: Union[str, Sequence[str], None] = 'c9e1f3a7b2d4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Agregar codigo_indicador (nuevo)
    op.add_column(
        'DIM_IndicadorTabla',
        sa.Column('codigo_indicador', sa.String(50), nullable=True),
        schema='Config',
    )
    # Ampliar nombre_indicador a 150 chars (era 100)
    op.alter_column(
        'DIM_IndicadorTabla', 'nombre_indicador',
        existing_type=sa.String(100),
        type_=sa.String(150),
        existing_nullable=True,
        schema='Config',
    )


def downgrade() -> None:
    op.drop_column('DIM_IndicadorTabla', 'codigo_indicador', schema='Config')
    op.alter_column(
        'DIM_IndicadorTabla', 'nombre_indicador',
        existing_type=sa.String(150),
        type_=sa.String(100),
        existing_nullable=True,
        schema='Config',
    )
