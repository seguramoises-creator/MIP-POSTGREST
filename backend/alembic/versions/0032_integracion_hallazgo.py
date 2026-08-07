"""Audit.IntegracionHallazgo — traza de validacion de lotes de Mallen.

El detalle fila a fila de la validacion no cabe en controlcarga.mensaje
(String(500)) y no debe vivir en `ext`, que es contrato con un tercero.

Revision ID: 0032_integracion_hallazgo
Revises: 0031_formacion_ampliada
Create Date: 2026-08-06
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0032_integracion_hallazgo"
down_revision: Union[str, Sequence[str], None] = "0031_formacion_ampliada"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "IntegracionHallazgo",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("lote_id", sa.BigInteger(), nullable=False),
        sa.Column("tabla", sa.String(length=40), nullable=False),
        sa.Column("origen_id", sa.String(length=60), nullable=True),
        sa.Column("campo", sa.String(length=40), nullable=True),
        sa.Column("problema", sa.String(length=300), nullable=False),
        sa.Column("severidad", sa.String(length=10), nullable=False),
        sa.Column("detectado_en", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["lote_id"], ["ext.controlcarga.lote_id"]),
        sa.PrimaryKeyConstraint("id"),
        schema="Audit",
    )
    op.create_index("IX_IntegHallazgo_lote", "IntegracionHallazgo", ["lote_id"],
                    unique=False, schema="Audit")


def downgrade() -> None:
    op.drop_index("IX_IntegHallazgo_lote", table_name="IntegracionHallazgo",
                  schema="Audit")
    op.drop_table("IntegracionHallazgo", schema="Audit")
