"""agregar tablas Config.DIM_CategoriaDesempeno y Config.DIM_KpiDashboard

Revision ID: b3d4e6a91c2f
Revises: fe258a595170
Create Date: 2026-06-07 00:00:00.000000

Crea las tablas nuevas Config.DIM_CategoriaDesempeno y Config.DIM_KpiDashboard
para soportar la importación de las hojas DIM_CATEGORIA_DESEMPENO y
DIM_KPI_DASHBOARD del Excel DIM_MIP_FINAL.xlsx.

Ambas son tablas de catálogo globales (sin FK a otras DIM, no dependen de país):
- DIM_CategoriaDesempeno: clasificación por rango de score (Excelente/Bueno/
  En Desarrollo/Crítico/Sin Datos) con color para el dashboard.
- DIM_KpiDashboard: catálogo de KPIs mostrados en los dashboards, con su
  página de origen y fórmula/tipo de cálculo.

Son tablas nuevas (no existían filas previas), por lo que no requieren
backfill: se crean directamente.

Modelos correspondientes: app/models/dimensiones.py -> CategoriaDesempeno, KpiDashboard
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3d4e6a91c2f'
down_revision: Union[str, Sequence[str], None] = 'fe258a595170'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'DIM_CategoriaDesempeno',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('codigo', sa.String(length=30), nullable=False),
        sa.Column('nombre', sa.String(length=100), nullable=False),
        sa.Column('score_min', sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column('score_max', sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column('color_dashboard', sa.String(length=30), nullable=True),
        sa.Column('activo', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint('codigo', name='UQ_CategoriaDesempeno_Codigo'),
        schema='Config',
    )

    op.create_table(
        'DIM_KpiDashboard',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('codigo', sa.String(length=50), nullable=False),
        sa.Column('nombre', sa.String(length=150), nullable=False),
        sa.Column('pagina_dashboard', sa.String(length=100), nullable=True),
        sa.Column('tipo_calculo', sa.String(length=50), nullable=True),
        sa.Column('descripcion', sa.Text(), nullable=True),
        sa.Column('activo', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint('codigo', name='UQ_KpiDashboard_Codigo'),
        schema='Config',
    )


def downgrade() -> None:
    op.drop_table('DIM_KpiDashboard', schema='Config')
    op.drop_table('DIM_CategoriaDesempeno', schema='Config')
