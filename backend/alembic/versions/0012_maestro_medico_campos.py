"""DIM_Medico: campos generales del Maestro de Médicos

Revision ID: 0012_maestro_medico_campos
Revises: 0011_rm_coaching_min_dia
Create Date: 2026-07-13
"""
from alembic import op
import sqlalchemy as sa

revision = "0012_maestro_medico_campos"
down_revision = "0012_usuario_email_opcional"
branch_labels = None
depends_on = None

_COLS = [
    ("telefono", sa.String(40), True, None),
    ("direccion", sa.String(300), True, None),
    ("sector", sa.String(100), True, None),
    ("exequatur", sa.String(50), True, None),
    ("observaciones", sa.String(500), True, None),
    ("estado_validacion", sa.String(16), False, "APROBADO"),
    ("origen", sa.String(16), False, "MANUAL"),
]


def upgrade() -> None:
    for nombre, tipo, nullable, default in _COLS:
        op.add_column("DIM_Medico",
            sa.Column(nombre, tipo, nullable=nullable, server_default=default),
            schema="Config")
    op.add_column("DIM_Medico",
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        schema="Config")
    op.add_column("DIM_Medico",
        sa.Column("updated_at", sa.DateTime(), nullable=True), schema="Config")
    op.create_index("IX_Medico_exequatur", "DIM_Medico", ["exequatur"], schema="Config")


def downgrade() -> None:
    op.drop_index("IX_Medico_exequatur", table_name="DIM_Medico", schema="Config")
    for nombre in ("updated_at", "created_at", "observaciones", "exequatur",
                   "sector", "direccion", "telefono", "origen", "estado_validacion"):
        op.drop_column("DIM_Medico", nombre, schema="Config")
