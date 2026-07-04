"""agregar pais_id a Config.DIM_Indicador

Esta es la migracion que corrige el drift real detectado: el modelo
`Indicador` (app/models/dimensiones.py) define `pais_id` como columna
NOT NULL con FK a Config.DIM_Pais, pero la tabla en la base de datos
nunca la tuvo -> causaba el error:
    pymssql.ProgrammingError: (207, b"Invalid column name 'pais_id'.")

Estrategia segura para no romper filas existentes:
  1. agregar la columna como NULL
  2. backfill (asignar un pais_id valido a las filas existentes)
  3. alterar a NOT NULL
  4. agregar la FK

IMPORTANTE: revisa el valor de backfill (`DEFAULT_PAIS_ID`) antes de
correr esto en un entorno con datos reales — debe ser el id de un
registro existente en Config.DIM_Pais que tenga sentido para tus
indicadores actuales (p.ej. el pais "global" o el primero que se cargo).

Revision ID: a1c4f9d2b6e0
Revises: fb61c3c89ec7
Create Date: 2026-06-06 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1c4f9d2b6e0'
down_revision: Union[str, Sequence[str], None] = 'fb61c3c89ec7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Ajusta este valor al id real de Config.DIM_Pais que deben usar los
# indicadores existentes que aun no tienen pais asignado.
DEFAULT_PAIS_ID = 1


def upgrade() -> None:
    # 1. Agregar columna como NULL (no rompe filas existentes)
    op.add_column(
        'DIM_Indicador',
        sa.Column('pais_id', sa.Integer(), nullable=True),
        schema='Config',
    )

    # 2. Backfill: asignar pais_id a las filas existentes
    op.execute(
        f"UPDATE [Config].[DIM_Indicador] SET pais_id = {DEFAULT_PAIS_ID} "
        f"WHERE pais_id IS NULL"
    )

    # 3. Alterar a NOT NULL ahora que todas las filas tienen valor
    op.alter_column(
        'DIM_Indicador', 'pais_id',
        existing_type=sa.Integer(),
        nullable=False,
        schema='Config',
    )

    # 4. Agregar la FK hacia Config.DIM_Pais
    op.create_foreign_key(
        'FK_Indicador_Pais',
        'DIM_Indicador', 'DIM_Pais',
        ['pais_id'], ['id'],
        source_schema='Config', referent_schema='Config',
    )


def downgrade() -> None:
    op.drop_constraint('FK_Indicador_Pais', 'DIM_Indicador', schema='Config', type_='foreignkey')
    op.drop_column('DIM_Indicador', 'pais_id', schema='Config')
