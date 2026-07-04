"""exam: agregar mapa_presentacion_json a FactIntentoExamen

Revision ID: a3f7c9e2d1b8
Revises: 798c1fe1eff9
Create Date: 2026-06-27 12:30:00.000000

Persiste el mapa de barajado de opciones por pregunta en el intento,
de modo que `responder` pueda traducir indice_presentado → opcion_id
sin necesidad de replay del RNG.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'a3f7c9e2d1b8'
down_revision: Union[str, Sequence[str], None] = '798c1fe1eff9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'FactIntentoExamen',
        sa.Column('mapa_presentacion_json', sa.Text(), nullable=True),
        schema='exam',
    )


def downgrade() -> None:
    op.drop_column('FactIntentoExamen', 'mapa_presentacion_json', schema='exam')
