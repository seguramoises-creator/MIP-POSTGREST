"""Fuente única de EVAL_CONOCIMIENTOS: dueño por país + notas capturadas a mano.

Revision ID: 0035_fuente_conocimientos
Revises: 0034_medicos_top
Create Date: 2026-08-12
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0035_fuente_conocimientos"
down_revision: Union[str, Sequence[str], None] = "0034_medicos_top"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "FuenteIndicador",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("pais_codigo", sa.String(length=10), nullable=False),
        sa.Column("indicador_codigo", sa.String(length=50), nullable=False),
        sa.Column("fuente", sa.String(length=20), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(), nullable=False),
        sa.Column("actualizado_por_usuario_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["pais_codigo"], ["Config.DIM_Pais.codigo"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("pais_codigo", "indicador_codigo",
                            name="UQ_FuenteIndicador_clave"),
        schema="Config",
    )

    # Semilla: cada país existente arranca en CAPTURA_MANUAL, que es lo más
    # parecido a lo que hace el Excel hoy. El servicio ya devolvería ese default
    # sin fila, pero sembrarla hace visible la decisión en la pantalla desde el
    # primer día — un país "sin configurar" invita a creer que nadie decidió.
    op.execute("""
        INSERT INTO "Config"."FuenteIndicador"
            (pais_codigo, indicador_codigo, fuente, actualizado_en)
        SELECT codigo, 'EVAL_CONOCIMIENTOS', 'CAPTURA_MANUAL', NOW()
          FROM "Config"."DIM_Pais"
    """)

    # SIN UNIQUE a proposito: un RM puede tener varias notas en un ciclo (temas
    # o fechas distintas) y al integrar se promedian. Ver el docstring del
    # modelo `NotaConocimiento` para la regla que eso obliga a sostener.
    op.create_table(
        "FACT_NotaConocimiento",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("pais_codigo", sa.String(length=10), nullable=False),
        sa.Column("ciclo_id", sa.Integer(), nullable=False),
        sa.Column("rm_id", sa.Integer(), nullable=False),
        sa.Column("fecha_evaluacion", sa.Date(), nullable=False),
        sa.Column("nota", sa.Numeric(precision=10, scale=4), nullable=False),
        sa.Column("tema", sa.String(length=200), nullable=True),
        sa.Column("capturado_por_usuario_id", sa.Integer(), nullable=True),
        sa.Column("capturado_en", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["pais_codigo"], ["Config.DIM_Pais.codigo"]),
        sa.ForeignKeyConstraint(["ciclo_id"], ["Config.DIM_Ciclo.id"]),
        sa.ForeignKeyConstraint(["rm_id"], ["Config.DIM_RM.id"]),
        sa.PrimaryKeyConstraint("id"),
        schema="DW",
    )
    op.create_index("IX_NotaConocimiento_ciclo", "FACT_NotaConocimiento",
                    ["ciclo_id", "rm_id"], schema="DW")


def downgrade() -> None:
    op.drop_index("IX_NotaConocimiento_ciclo", table_name="FACT_NotaConocimiento",
                  schema="DW")
    op.drop_table("FACT_NotaConocimiento", schema="DW")
    op.drop_table("FuenteIndicador", schema="Config")
