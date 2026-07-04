"""Merge heads: e2f5b9c4a1d8 + a9b3c7d2e5f1

Revision ID: f3g6h9j2k5l8
Revises: e2f5b9c4a1d8, a9b3c7d2e5f1
Create Date: 2026-06-12

Merge de las dos ramas activas:
  - e2f5b9c4a1d8: SP sp_CompletarPuntajesCiclo — factor × peso en runtime
  - a9b3c7d2e5f1: Tabla staging ETL.FACT_KPI_RAW
"""
from typing import Sequence, Union
from alembic import op

revision: str = 'f3g6h9j2k5l8'
down_revision: Union[str, Sequence[str], None] = ('e2f5b9c4a1d8', 'a9b3c7d2e5f1')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
