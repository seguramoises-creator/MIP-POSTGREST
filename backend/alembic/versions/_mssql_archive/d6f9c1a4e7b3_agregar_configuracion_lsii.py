"""agregar tabla Config.DIM_ConfiguracionLSII (umbral D1-D4 editable)

Revision ID: d6f9c1a4e7b3
Revises: c5f8a2e6b9d1
Create Date: 2026-06-17 00:00:00.000000

Permite que un ADMIN/GERENTE_PRODUCTIVIDAD ajuste desde la aplicación
(sin tocar la base de datos) los puntos de corte que definen los
cuadrantes D1-D4 de la Matriz LSII. Antes estaban fijos en código
(CORTE_DESEMPENO = 80, CORTE_RECEPTIVIDAD = 80 en lsii_service.py).

Se crea una tabla con una sola fila de configuración global, sembrada
con los valores por defecto (80 / 80) para no alterar el comportamiento
actual del sistema.
"""
from typing import Sequence, Union
import datetime as dt

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd6f9c1a4e7b3'
down_revision: Union[str, Sequence[str], None] = 'c5f8a2e6b9d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'DIM_ConfiguracionLSII',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('corte_desempeno', sa.Numeric(precision=5, scale=2), nullable=False, server_default='80'),
        sa.Column('corte_receptividad', sa.Numeric(precision=5, scale=2), nullable=False, server_default='80'),
        sa.Column('actualizado_en', sa.DateTime(), nullable=False),
        sa.Column('actualizado_por', sa.String(length=100), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        schema='Config',
    )

    tabla_config = sa.table(
        'DIM_ConfiguracionLSII',
        sa.column('corte_desempeno', sa.Numeric),
        sa.column('corte_receptividad', sa.Numeric),
        sa.column('actualizado_en', sa.DateTime),
        sa.column('actualizado_por', sa.String),
        schema='Config',
    )
    op.bulk_insert(tabla_config, [{
        "corte_desempeno": 80,
        "corte_receptividad": 80,
        "actualizado_en": dt.datetime.utcnow(),
        "actualizado_por": "migracion_seed",
    }])


def downgrade() -> None:
    op.drop_table('DIM_ConfiguracionLSII', schema='Config')
