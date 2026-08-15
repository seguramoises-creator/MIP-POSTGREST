"""Alcances por línea y por país: FACT_UsuarioPais + DIM_GerenteLinea.

El backfill copia `DIM_Gerente.linea_id` a `DIM_GerenteLinea` para que ningún
gerente pierda su línea al cambiar la fuente de verdad. `DIM_Gerente.linea_id`
NO se borra: sigue habiendo código que lo lee.

`FACT_UsuarioPais` nace VACÍA a propósito — sin filas significa "todos los
países", así que los usuarios existentes conservan su acceso actual.

Revision ID: 0036_alcance_linea_pais
Revises: 0035_fuente_conocimientos
"""
import sqlalchemy as sa
from alembic import op

revision = "0036_alcance_linea_pais"
down_revision = "0035_fuente_conocimientos"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "FACT_UsuarioPais",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("pais_codigo", sa.String(length=10), nullable=False),
        sa.ForeignKeyConstraint(["usuario_id"], ["Security.DIM_Usuario.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("usuario_id", "pais_codigo", name="UQ_UsuarioPais"),
        schema="Security",
    )
    # Nombre igual al que SQLAlchemy genera solo para `index=True` sin nombre
    # explícito (incluye el esquema) — así `alembic check` no ve diferencia
    # entre lo que crea esta migración y lo que describe el modelo.
    op.create_index("ix_Security_FACT_UsuarioPais_usuario_id", "FACT_UsuarioPais", ["usuario_id"], schema="Security")

    op.create_table(
        "DIM_GerenteLinea",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("gerente_id", sa.Integer(), nullable=False),
        sa.Column("linea_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["gerente_id"], ["Config.DIM_Gerente.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["linea_id"], ["Config.DIM_Linea.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("gerente_id", "linea_id", name="UQ_GerenteLinea"),
        schema="Config",
    )
    op.create_index("ix_Config_DIM_GerenteLinea_gerente_id", "DIM_GerenteLinea", ["gerente_id"], schema="Config")
    op.create_index("ix_Config_DIM_GerenteLinea_linea_id", "DIM_GerenteLinea", ["linea_id"], schema="Config")

    # Backfill: la línea que cada gerente ya tenía.
    op.execute("""
        INSERT INTO "Config"."DIM_GerenteLinea" (gerente_id, linea_id)
        SELECT id, linea_id FROM "Config"."DIM_Gerente" WHERE linea_id IS NOT NULL
    """)


def downgrade() -> None:
    op.drop_index("ix_Config_DIM_GerenteLinea_linea_id", table_name="DIM_GerenteLinea", schema="Config")
    op.drop_index("ix_Config_DIM_GerenteLinea_gerente_id", table_name="DIM_GerenteLinea", schema="Config")
    op.drop_table("DIM_GerenteLinea", schema="Config")
    op.drop_index("ix_Security_FACT_UsuarioPais_usuario_id", table_name="FACT_UsuarioPais", schema="Security")
    op.drop_table("FACT_UsuarioPais", schema="Security")
