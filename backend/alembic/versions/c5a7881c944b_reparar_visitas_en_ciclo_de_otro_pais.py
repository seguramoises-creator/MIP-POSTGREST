"""reparar visitas en ciclo de otro pais

Revision ID: c5a7881c944b
Revises: 9f25f1067bc2
Create Date: 2026-07-07 02:26:08.266208

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c5a7881c944b'
down_revision: Union[str, Sequence[str], None] = '9f25f1067bc2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Reparación de datos: visitas y muestras registradas en el ciclo de OTRO país.

    El default de ciclo del módulo Visita tomaba el ciclo más reciente GLOBAL
    (sin filtrar por país ni por abierto), por lo que registros de un VM de DO
    podían caer en un ciclo de CR/VE/etc. Se mueven al ciclo ABIERTO más
    reciente del país del VM. (El código ya quedó corregido — esto sanea lo
    histórico.)"""
    op.execute('''
        UPDATE "Visita"."FactVisita" f
        SET ciclo_id = sub.abierto_id
        FROM "Config"."DIM_RM" rm,
             "Config"."DIM_Ciclo" c1,
             LATERAL (
               SELECT c.id AS abierto_id FROM "Config"."DIM_Ciclo" c
               WHERE c.pais_codigo = rm.pais_codigo AND c.cerrado = false
               ORDER BY c.anio DESC, c.numero DESC LIMIT 1
             ) sub
        WHERE rm.id = f.vm_id
          AND c1.id = f.ciclo_id
          AND c1.pais_codigo <> rm.pais_codigo
    ''')
    op.execute('''
        UPDATE "Visita"."MuestraEntregada" m
        SET ciclo_id = sub.abierto_id
        FROM "Config"."DIM_RM" rm,
             "Config"."DIM_Ciclo" c1,
             LATERAL (
               SELECT c.id AS abierto_id FROM "Config"."DIM_Ciclo" c
               WHERE c.pais_codigo = rm.pais_codigo AND c.cerrado = false
               ORDER BY c.anio DESC, c.numero DESC LIMIT 1
             ) sub
        WHERE rm.id = m.vm_id
          AND c1.id = m.ciclo_id
          AND c1.pais_codigo <> rm.pais_codigo
    ''')


def downgrade() -> None:
    """No aplica: no se puede reconstruir el ciclo erróneo original."""
    pass
