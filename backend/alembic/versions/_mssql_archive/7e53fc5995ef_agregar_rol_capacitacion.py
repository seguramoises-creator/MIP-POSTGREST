"""agregar rol CAPACITACION

Revision ID: 7e53fc5995ef
Revises: 7fc6c15162a2
Create Date: 2026-06-27 01:47:58.697965

"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = '7e53fc5995ef'
down_revision: Union[str, Sequence[str], None] = '7fc6c15162a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_VALORES_NUEVOS = (
    "'ADMIN','PRESIDENCIA','DIR_COMERCIAL','GERENTE_PRODUCTIVIDAD',"
    "'GERENTE_DISTRITO','GERENTE_MARCA','REPRESENTANTE_MEDICO','CONSULTA','CAPACITACION'"
)
_VALORES_VIEJOS = (
    "'ADMIN','PRESIDENCIA','DIR_COMERCIAL','GERENTE_PRODUCTIVIDAD',"
    "'GERENTE_DISTRITO','GERENTE_MARCA','REPRESENTANTE_MEDICO','CONSULTA'"
)


def _nombre_check(conn):
    row = conn.execute(text(
        "SELECT cc.name FROM sys.check_constraints cc "
        "JOIN sys.columns c ON c.object_id=cc.parent_object_id AND c.column_id=cc.parent_column_id "
        "WHERE cc.parent_object_id=OBJECT_ID('Security.DIM_Usuario') AND c.name='rol'"
    )).fetchone()
    return row[0] if row else None


def upgrade() -> None:
    conn = op.get_bind()
    nombre = _nombre_check(conn)
    if nombre:
        conn.execute(text(f"ALTER TABLE [Security].[DIM_Usuario] DROP CONSTRAINT [{nombre}]"))
    conn.execute(text(
        f"ALTER TABLE [Security].[DIM_Usuario] ADD CONSTRAINT CK_DIM_Usuario_rol "
        f"CHECK (rol IN ({_VALORES_NUEVOS}))"
    ))


def downgrade() -> None:
    conn = op.get_bind()
    nombre = _nombre_check(conn)
    if nombre:
        conn.execute(text(f"ALTER TABLE [Security].[DIM_Usuario] DROP CONSTRAINT [{nombre}]"))
    conn.execute(text(
        f"ALTER TABLE [Security].[DIM_Usuario] ADD CONSTRAINT CK_DIM_Usuario_rol "
        f"CHECK (rol IN ({_VALORES_VIEJOS}))"
    ))
