"""Medicos TOP: es_top en el panel de visita + tabla de avisos enviados.

Revision ID: 0034_medicos_top
Revises: 0033_mapeo_externo
Create Date: 2026-08-09
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0034_medicos_top"
down_revision: Union[str, Sequence[str], None] = "0033_mapeo_externo"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # NOT NULL con server_default: la tabla tiene datos reales en produccion y
    # sin default el ALTER fallaria. `false` es la semantica correcta —
    # ausencia de dato = NO es TOP (ver spec §2).
    op.add_column(
        "DIM_MedicoVisita",
        sa.Column("es_top", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        schema="Visita",
    )
    op.create_table(
        "AvisoTopEnviado",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("vm_id", sa.Integer(), nullable=False),
        sa.Column("ciclo_id", sa.Integer(), nullable=False),
        sa.Column("medico_id", sa.Integer(), nullable=False),
        sa.Column("tipo_visita", sa.CHAR(length=1), nullable=False),
        sa.Column("tipo_aviso", sa.String(length=20), nullable=False),
        sa.Column("fecha_envio", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["vm_id"], ["Config.DIM_RM.id"]),
        sa.ForeignKeyConstraint(["ciclo_id"], ["Config.DIM_Ciclo.id"]),
        sa.ForeignKeyConstraint(["medico_id"], ["Visita.DIM_MedicoVisita.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("vm_id", "ciclo_id", "medico_id", "tipo_visita", "tipo_aviso",
                            name="UQ_AvisoTop_clave"),
        schema="Visita",
    )


def downgrade() -> None:
    op.drop_table("AvisoTopEnviado", schema="Visita")
    op.drop_column("DIM_MedicoVisita", "es_top", schema="Visita")
