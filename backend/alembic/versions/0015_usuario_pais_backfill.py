"""backfill del pais de los usuarios (sin pais, la tienda Pais+Ciclo no arranca)

Revision ID: 0015_usuario_pais_backfill
Revises: 0014_reparar_ciclo_coaching
Create Date: 2026-07-16

"""
from typing import Sequence, Union

from alembic import op

revision: str = '0015_usuario_pais_backfill'
down_revision: Union[str, Sequence[str], None] = '0014_reparar_ciclo_coaching'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Mismo listado que `ROLES_MULTIPAIS` en admin.py y en ciclo.store.ts.
MULTIPAIS = "('ADMIN','PRESIDENCIA','DIR_COMERCIAL','GERENTE_PRODUCTIVIDAD')"


def upgrade() -> None:
    """Reparación de datos: usuarios sin `pais_codigo`.

    `ciclo.store.init()` hace `paises = me.pais_codigo ? [me.pais_codigo] : []` para los roles
    NO multipaís. Sin país nunca llama a `setPais()`, así que la tienda de País+Ciclo queda
    vacía: sin badge, sin `cicloId`, sin lista de ciclos. Falla en silencio — nada da error,
    cada módulo se las arregla con un fallback y el usuario ve menos de lo que debería. En
    producción estaban así 7 de 9 representantes.

    El dato no falta, está a un salto: el país de un representante es el de su RM, y el de un
    gerente el de su gerente. Se deriva en ese orden y solo al final se cae al país con
    operación (el de más RMs) — la misma regla que ya usa `GET /admin/pais-defecto`, para no
    hardcodear un país en un sistema multipaís.

    Los roles multipaís se dejan intactos: para ellos el país propio es opcional a propósito.
    """
    # 1. El país del representante es el de su RM.
    op.execute('''
        UPDATE "Security"."DIM_Usuario" u SET pais_codigo = rm.pais_codigo
        FROM "Config"."DIM_RM" rm
        WHERE rm.id = u.rm_id AND u.pais_codigo IS NULL AND rm.pais_codigo IS NOT NULL
    ''')
    # 2. El del gerente de distrito es el de su gerente.
    op.execute('''
        UPDATE "Security"."DIM_Usuario" u SET pais_codigo = g.pais_codigo
        FROM "Config"."DIM_Gerente" g
        WHERE g.id = u.gerente_id AND u.pais_codigo IS NULL AND g.pais_codigo IS NOT NULL
    ''')
    # 3. El resto NO multipaís (Capacitación, Consulta…) no tiene de dónde derivarlo: se les
    #    asigna el país con operación. `rol` es un ENUM de PostgreSQL — hay que castear a texto.
    op.execute(f'''
        UPDATE "Security"."DIM_Usuario" u
        SET pais_codigo = (SELECT pais_codigo FROM "Config"."DIM_RM"
                           WHERE pais_codigo IS NOT NULL
                           GROUP BY pais_codigo ORDER BY COUNT(*) DESC LIMIT 1)
        WHERE u.pais_codigo IS NULL AND u.rol::text NOT IN {MULTIPAIS}
    ''')


def downgrade() -> None:
    """No aplica: no se puede saber cuáles estaban en NULL a propósito."""
    pass
