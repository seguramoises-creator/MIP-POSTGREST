"""crear tabla Security FACT_TokenRevocado blacklist

Revision ID: 7fc6c15162a2
Revises: d4e8f1b5c2a9
Create Date: 2026-06-26 20:17:47.430166

Persiste la blacklist de refresh tokens en BD (FIX W-04 v2). La versión previa
vivía en un `set` en memoria que no se compartía entre workers de uvicorn ni
sobrevivía a reinicios. Esta tabla la reemplaza.

Idempotente: crea esquema, tabla e índices solo si no existen (estilo defensivo
usado en el resto de migraciones del proyecto).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = '7fc6c15162a2'
down_revision: Union[str, Sequence[str], None] = 'd4e8f1b5c2a9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tabla_existe(conn, schema: str, table: str) -> bool:
    row = conn.execute(
        text(
            "SELECT 1 FROM INFORMATION_SCHEMA.TABLES "
            "WHERE TABLE_SCHEMA = :s AND TABLE_NAME = :t"
        ),
        {"s": schema, "t": table},
    ).fetchone()
    return row is not None


def upgrade() -> None:
    conn = op.get_bind()

    # Esquema Security (por si la BD aún no lo tuviera)
    conn.execute(text(
        "IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'Security') "
        "EXEC('CREATE SCHEMA [Security]')"
    ))

    if not _tabla_existe(conn, 'Security', 'FACT_TokenRevocado'):
        op.create_table(
            'FACT_TokenRevocado',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('jti', sa.String(length=255), nullable=False),
            sa.Column('usuario_id', sa.Integer(), nullable=True),
            sa.Column('motivo', sa.String(length=40), nullable=True),
            sa.Column('expira_en', sa.DateTime(), nullable=False),
            sa.Column('revocado_en', sa.DateTime(), nullable=True),
            schema='Security',
        )
        # jti único: una sola fila por token revocado
        conn.execute(text(
            "CREATE UNIQUE INDEX UX_FACT_TokenRevocado_jti "
            "ON [Security].[FACT_TokenRevocado] (jti)"
        ))
        # expira_en: acelera la purga de tokens ya expirados
        conn.execute(text(
            "CREATE INDEX IX_FACT_TokenRevocado_expira_en "
            "ON [Security].[FACT_TokenRevocado] (expira_en)"
        ))


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS IX_FACT_TokenRevocado_expira_en ON [Security].[FACT_TokenRevocado]")
    op.execute("DROP INDEX IF EXISTS UX_FACT_TokenRevocado_jti ON [Security].[FACT_TokenRevocado]")
    op.drop_table('FACT_TokenRevocado', schema='Security')
