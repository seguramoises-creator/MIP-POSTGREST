"""reparar el ciclo de las hojas de coaching (lo define su fecha)

Revision ID: 0014_reparar_ciclo_coaching
Revises: 0013_medicovisita_maestro_fk
Create Date: 2026-07-16

"""
from typing import Sequence, Union

from alembic import op

revision: str = '0014_reparar_ciclo_coaching'
down_revision: Union[str, Sequence[str], None] = '0013_medicovisita_maestro_fk'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Reparación de datos: hojas de coaching archivadas en el ciclo equivocado.

    El ciclo de la hoja se resolvía con `ciclo_por_defecto` (el ciclo ABIERTO de número
    más alto del país) en vez de por la FECHA del coaching. Con C12 abierto, una hoja del
    10-jul quedó archivada en C12-2026 (diciembre), porque 12 > 7. El código ya está
    corregido (`coaching_more_service._ciclo_pais_de_rm`); esto sanea lo histórico.

    `coaching."Sesion"` es append-only: un trigger rechaza UPDATE/DELETE para que ninguna
    ruta de la aplicación pueda reescribir una hoja firmada. Una migración versionada y
    revisada es la única vía legítima para corregir el dato, así que se desactiva el
    trigger solo durante el UPDATE. El DDL de PostgreSQL es transaccional: si algo falla,
    el rollback deja el trigger activo — no puede quedar desprotegida la tabla.

    Solo se toca `ciclo_id`. El contenido de la hoja (calificaciones, plan, firma) queda
    intacto: la inmutabilidad de lo que el GD y el RM acordaron y firmaron se respeta.
    """
    op.execute('ALTER TABLE coaching."Sesion" DISABLE TRIGGER trg_coaching_sesion_inmutable')
    op.execute('''
        UPDATE coaching."Sesion" s
        SET ciclo_id = c.id
        FROM "Config"."DIM_Ciclo" c
        WHERE c.pais_codigo = s.pais_codigo
          AND s.fecha_coaching BETWEEN c.fecha_inicio AND c.fecha_fin
          AND s.ciclo_id IS DISTINCT FROM c.id
    ''')
    op.execute('ALTER TABLE coaching."Sesion" ENABLE TRIGGER trg_coaching_sesion_inmutable')


def downgrade() -> None:
    """No aplica: el ciclo erróneo original no se puede reconstruir (ni tendría sentido)."""
    pass
