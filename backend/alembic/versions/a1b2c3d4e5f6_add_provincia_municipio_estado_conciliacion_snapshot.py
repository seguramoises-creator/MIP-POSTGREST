"""add_provincia_municipio_estado_conciliacion_snapshot

Revision ID: a1b2c3d4e5f6
Revises: f7b2c9a48d1e
Create Date: 2026-06-24 22:00:00.000000

Agrega las columnas Provincia, Municipio y EstadoConciliacion
a cat.FactMedicoCategoriaSnapshot que faltaban en la DB.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = 'b1d4e7f2a9c3'
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

    if not _col_exists('FactMedicoCategoriaSnapshot', 'Provincia'):
        op.add_column(
            'FactMedicoCategoriaSnapshot',
            sa.Column('Provincia', sa.String(120), nullable=True),
            schema='cat',
        )
    if not _col_exists('FactMedicoCategoriaSnapshot', 'Municipio'):
        op.add_column(
            'FactMedicoCategoriaSnapshot',
            sa.Column('Municipio', sa.String(120), nullable=True),
            schema='cat',
        )
    if not _col_exists('FactMedicoCategoriaSnapshot', 'EstadoConciliacion'):
        op.add_column(
            'FactMedicoCategoriaSnapshot',
            sa.Column('EstadoConciliacion', sa.String(30), nullable=True),
            schema='cat',
        )


def downgrade() -> None:
    op.drop_column('FactMedicoCategoriaSnapshot', 'EstadoConciliacion', schema='cat')
    op.drop_column('FactMedicoCategoriaSnapshot', 'Municipio', schema='cat')
    op.drop_column('FactMedicoCategoriaSnapshot', 'Provincia', schema='cat')
