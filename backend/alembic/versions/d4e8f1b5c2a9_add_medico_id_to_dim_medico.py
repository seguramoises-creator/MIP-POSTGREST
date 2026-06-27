"""add_medico_id_to_dim_medico

Revision ID: d4e8f1b5c2a9
Revises: a2c5e8f1b3d7
Create Date: 2026-06-25 21:00:00.000000

Agrega columna MedicoId (INT nullable) a cat.DimMedico.
Esta columna almacena el ID numérico del médico proveniente del Excel
de Cobertura Predictiva y sirve como llave de negocio para vincular
FactTargetMedicoCiclo y FactVisitaMedica con el catálogo de médicos.
"""
from alembic import op
import sqlalchemy as sa

revision = 'd4e8f1b5c2a9'
down_revision = 'a2c5e8f1b3d7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    from sqlalchemy import text
    conn = op.get_bind()

    def _col_exists(table: str, col: str) -> bool:
        row = conn.execute(
            text(
                "SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS "
                "WHERE TABLE_SCHEMA='cat' AND TABLE_NAME=:t AND COLUMN_NAME=:c"
            ),
            {"t": table, "c": col},
        ).fetchone()
        return row is not None

    if not _col_exists('DimMedico', 'MedicoId'):
        op.add_column(
            'DimMedico',
            sa.Column('MedicoId', sa.Integer(), nullable=True),
            schema='cat',
        )
        # Índice no-único para búsquedas rápidas por ID de negocio
        conn.execute(text(
            "CREATE INDEX IX_DimMedico_MedicoId ON [cat].[DimMedico] (MedicoId) "
            "WHERE MedicoId IS NOT NULL"
        ))


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS IX_DimMedico_MedicoId ON [cat].[DimMedico]")
    op.drop_column('DimMedico', 'MedicoId', schema='cat')
