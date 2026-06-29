"""add peso to exam.DimPregunta (VISTA weighted scoring, base 100)

Revision ID: c7e1a9b3f240
Revises: 09529c330972
Create Date: 2026-06-29

Agrega la columna `peso` (Numeric base 100) a las preguntas. NULL = reparto
automático igual (100 ÷ N). Si se asignan pesos manuales, su suma por examen
debe ser 100 (validado al publicar). Idempotente: no falla si la columna ya existe.
"""
from alembic import op
import sqlalchemy as sa

revision = "c7e1a9b3f240"
down_revision = "09529c330972"
branch_labels = None
depends_on = None


def _tiene_columna(insp, schema, tabla, col):
    return any(c["name"] == col for c in insp.get_columns(tabla, schema=schema))


def upgrade():
    insp = sa.inspect(op.get_bind())
    if not _tiene_columna(insp, "exam", "DimPregunta", "peso"):
        op.add_column(
            "DimPregunta",
            sa.Column("peso", sa.Numeric(6, 2), nullable=True),
            schema="exam",
        )


def downgrade():
    insp = sa.inspect(op.get_bind())
    if _tiene_columna(insp, "exam", "DimPregunta", "peso"):
        op.drop_column("DimPregunta", "peso", schema="exam")
