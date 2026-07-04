"""corregir UNIQUE constraint de Config.DIM_Indicador (codigo -> pais_id+codigo)

Revision ID: c7f2a93d5e1b
Revises: 8a3690f43e28
Create Date: 2026-06-06 05:00:00.000000

Drift detectado al probar la importacion de Excel: la tabla tenia una
restriccion UNIQUE heredada solo sobre `codigo`
(`UQ__DIM_Indi__40F9A20658D63B90`, nombre auto-generado por SQL Server),
de la epoca en que la tabla no tenia columna `pais_id` y los codigos de
indicador eran unicos a nivel global.

Ahora que cada pais define sus propios indicadores (columna `pais_id`
agregada en la migracion a1c4f9d2b6e0), el mismo `codigo` puede repetirse
legitimamente entre paises distintos — la unicidad real debe ser sobre
la combinacion (pais_id, codigo). Esto es justo lo que espera la logica
de importacion en app/api/v1/routers/dims.py (busca duplicados con
`Indicador.pais_id == pais_id, Indicador.codigo == codigo`).

Sin este cambio, importar el mismo codigo para un segundo pais fallaba con:
    IntegrityError 2627 - Violation of UNIQUE KEY constraint
    'UQ__DIM_Indi__40F9A20658D63B90' ... duplicate key value is (COB_MD_F2)

El modelo `Indicador` ahora declara explicitamente
`UniqueConstraint("pais_id", "codigo", name="UQ_Indicador_Pais_Codigo")`
para que esta regla quede versionada y `alembic check` la detecte si
alguna vez se desincroniza de nuevo.

IMPORTANTE: si ya existen filas con el mismo `codigo` para el mismo
`pais_id` (no deberia, dado que la restriccion vieja era mas estricta),
`create_unique_constraint` fallara — revisa con:
    SELECT pais_id, codigo, COUNT(*) FROM [Config].[DIM_Indicador]
    GROUP BY pais_id, codigo HAVING COUNT(*) > 1
antes de aplicar en un entorno con datos reales.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7f2a93d5e1b'
down_revision: Union[str, Sequence[str], None] = '8a3690f43e28'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Nombre auto-generado por SQL Server para la restriccion vieja (visible en
# el mensaje de error de IntegrityError 2627). Si en tu entorno el nombre
# es distinto, ajustalo aqui antes de correr la migracion.
OLD_CONSTRAINT_NAME = "UQ__DIM_Indi__40F9A20658D63B90"
NEW_CONSTRAINT_NAME = "UQ_Indicador_Pais_Codigo"


def upgrade() -> None:
    # 1. Quitar la restriccion vieja (unicidad global sobre `codigo`)
    op.execute(
        f"ALTER TABLE [Config].[DIM_Indicador] "
        f"DROP CONSTRAINT [{OLD_CONSTRAINT_NAME}]"
    )

    # 2. Crear la restriccion correcta: unicidad por (pais_id, codigo)
    op.create_unique_constraint(
        NEW_CONSTRAINT_NAME,
        'DIM_Indicador',
        ['pais_id', 'codigo'],
        schema='Config',
    )


def downgrade() -> None:
    op.drop_constraint(NEW_CONSTRAINT_NAME, 'DIM_Indicador', schema='Config', type_='unique')
    op.create_unique_constraint(
        OLD_CONSTRAINT_NAME,
        'DIM_Indicador',
        ['codigo'],
        schema='Config',
    )
