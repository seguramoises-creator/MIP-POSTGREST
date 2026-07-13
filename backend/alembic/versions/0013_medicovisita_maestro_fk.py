"""DIM_MedicoVisita: FK maestro_medico_id → Config.DIM_Medico

Revision ID: 0013_medicovisita_maestro_fk
Revises: 0012_maestro_medico_campos
Create Date: 2026-07-13
"""
from alembic import op
import sqlalchemy as sa

revision = "0013_medicovisita_maestro_fk"
down_revision = "0012_maestro_medico_campos"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("DIM_MedicoVisita",
        sa.Column("maestro_medico_id", sa.Integer(), nullable=True),
        schema="Visita")
    op.create_index("IX_MedicoVisita_maestro", "DIM_MedicoVisita",
                    ["maestro_medico_id"], schema="Visita")
    op.create_foreign_key(
        "FK_MedicoVisita_maestro", "DIM_MedicoVisita", "DIM_Medico",
        ["maestro_medico_id"], ["id"],
        source_schema="Visita", referent_schema="Config")


def downgrade() -> None:
    op.drop_constraint("FK_MedicoVisita_maestro", "DIM_MedicoVisita",
                       schema="Visita", type_="foreignkey")
    op.drop_index("IX_MedicoVisita_maestro", table_name="DIM_MedicoVisita",
                  schema="Visita")
    op.drop_column("DIM_MedicoVisita", "maestro_medico_id", schema="Visita")
