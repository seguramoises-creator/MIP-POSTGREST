"""backfill debe_cambiar_password legacy

Revision ID: 9f25f1067bc2
Revises: c08a3407a342
Create Date: 2026-07-06 20:29:59.300091

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9f25f1067bc2'
down_revision: Union[str, Sequence[str], None] = 'c08a3407a342'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Los usuarios EXISTENTES no deben ser forzados a cambiar contraseña.

    El campo debe_cambiar_password existía desde el inicio con default True,
    pero ningún flujo lo leía — al activarse la política de contraseñas, todo
    el histórico quedó marcado como "primer login" y forzaba el cambio en cada
    inicio de sesión. Se limpia el flag heredado: la política de primer login
    aplica solo a usuarios creados a partir de ahora (el alta lo marca True
    explícitamente en admin.create_usuario)."""
    op.execute('UPDATE "Security"."DIM_Usuario" SET debe_cambiar_password = false')


def downgrade() -> None:
    """No aplica: no se puede distinguir el valor previo por usuario."""
    pass
