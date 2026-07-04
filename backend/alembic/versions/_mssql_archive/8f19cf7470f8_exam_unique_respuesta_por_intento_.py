"""exam unique respuesta por intento-pregunta

Revision ID: 8f19cf7470f8
Revises: a3f7c9e2d1b8
Create Date: 2026-06-27 16:36:08.951165

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8f19cf7470f8'
down_revision: Union[str, Sequence[str], None] = 'a3f7c9e2d1b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Crea un índice UNIQUE en (intento_id, pregunta_id) de FactIntentoRespuesta.

    Idempotente: solo crea el índice si no existe, usando IF NOT EXISTS.
    Defense-in-depth para que registrar_respuesta (que hace DELETE-then-INSERT)
    nunca pueda acumular duplicados incluso ante llamadas concurrentes.
    """
    op.execute(
        "IF NOT EXISTS ("
        "  SELECT 1 FROM sys.indexes"
        "  WHERE name = 'UQ_IntentoRespuesta_intento_pregunta'"
        "    AND object_id = OBJECT_ID('[exam].[FactIntentoRespuesta]')"
        ") "
        "CREATE UNIQUE INDEX UQ_IntentoRespuesta_intento_pregunta "
        "ON [exam].[FactIntentoRespuesta] (intento_id, pregunta_id)"
    )


def downgrade() -> None:
    """Elimina el índice UNIQUE de FactIntentoRespuesta."""
    op.execute(
        "DROP INDEX IF EXISTS UQ_IntentoRespuesta_intento_pregunta "
        "ON [exam].[FactIntentoRespuesta]"
    )
