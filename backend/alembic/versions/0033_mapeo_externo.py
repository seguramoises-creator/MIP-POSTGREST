"""Config.MapeoExterno — equivalencias entre codigos de Mallen e ids de VISTA.

Ninguna DIM_* se modifica: el mapeo vive en su propia tabla para no tocar
catalogos con datos reales en produccion.

Revision ID: 0033_mapeo_externo
Revises: 0032_integracion_hallazgo
Create Date: 2026-08-08
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0033_mapeo_externo"
down_revision: Union[str, Sequence[str], None] = "0032_integracion_hallazgo"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "MapeoExterno",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("entidad", sa.String(length=30), nullable=False),
        sa.Column("pais_codigo", sa.String(length=10), nullable=False),
        sa.Column("codigo_externo", sa.String(length=60), nullable=False),
        sa.Column("id_interno", sa.Integer(), nullable=False),
        sa.Column("sincronizado_en", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("entidad", "pais_codigo", "codigo_externo",
                            name="UQ_MapeoExterno_clave"),
        schema="Config",
    )


def downgrade() -> None:
    op.drop_table("MapeoExterno", schema="Config")
