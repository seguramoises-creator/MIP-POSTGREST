"""agregar tabla Config.DIM_MetaIndicador

Revision ID: fe258a595170
Revises: c7f2a93d5e1b
Create Date: 2026-06-07 00:00:00.000000

Crea la tabla nueva Config.DIM_MetaIndicador para soportar la importación de
la hoja DIM_META_INDICADOR (estructura V3) del Excel DIM_MIP_FINAL.xlsx.

Esta hoja define, por indicador, sus metas/umbrales y parámetros de cálculo
usados por los dashboards: PESO, MINIMO, OBJETIVO, MAXIMO, PUNTAJE_MAXIMO,
META_100, TIPO_CALCULO y ORDEN_DASHBOARD.

Es una tabla nueva (no existían filas previas), por lo que no requiere
backfill: se crea directamente con la columna FK NOT NULL.

Modelo correspondiente: app/models/dimensiones.py -> MetaIndicador
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fe258a595170'
down_revision: Union[str, Sequence[str], None] = 'c7f2a93d5e1b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'DIM_MetaIndicador',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('indicador_id', sa.Integer(), nullable=False),
        sa.Column('peso', sa.Numeric(precision=6, scale=2), nullable=False, server_default='0'),
        sa.Column('minimo', sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column('objetivo', sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column('maximo', sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column('puntaje_maximo', sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column('meta_100', sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column('tipo_calculo', sa.String(length=30), nullable=True),
        sa.Column('orden_dashboard', sa.Integer(), nullable=True),
        sa.Column('activo', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(
            ['indicador_id'], ['Config.DIM_Indicador.id'],
            name='FK_MetaIndicador_Indicador',
        ),
        sa.UniqueConstraint('indicador_id', name='UQ_MetaIndicador_Indicador'),
        schema='Config',
    )


def downgrade() -> None:
    op.drop_table('DIM_MetaIndicador', schema='Config')
