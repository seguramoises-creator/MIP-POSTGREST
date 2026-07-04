"""add respuesta_texto + puntos to exam.FactIntentoRespuesta (VISTA preguntas abiertas)

Revision ID: d4b8c1f6a920
Revises: c7e1a9b3f240
Create Date: 2026-06-29

Soporte de preguntas abiertas / caso-abierto: guarda la respuesta de texto libre
del evaluado (`respuesta_texto`) y los puntos otorgados manualmente por el Gerente
(`puntos`, NULL = pendiente de calificar). Idempotente.
"""
from alembic import op
import sqlalchemy as sa

revision = "d4b8c1f6a920"
down_revision = "c7e1a9b3f240"
branch_labels = None
depends_on = None

_TABLA = "FactIntentoRespuesta"
_SCHEMA = "exam"


def _cols(insp):
    return {c["name"] for c in insp.get_columns(_TABLA, schema=_SCHEMA)}


def upgrade():
    insp = sa.inspect(op.get_bind())
    cols = _cols(insp)
    if "respuesta_texto" not in cols:
        op.add_column(_TABLA, sa.Column("respuesta_texto", sa.Text(), nullable=True), schema=_SCHEMA)
    if "puntos" not in cols:
        op.add_column(_TABLA, sa.Column("puntos", sa.Numeric(6, 2), nullable=True), schema=_SCHEMA)


def downgrade():
    insp = sa.inspect(op.get_bind())
    cols = _cols(insp)
    if "puntos" in cols:
        op.drop_column(_TABLA, "puntos", schema=_SCHEMA)
    if "respuesta_texto" in cols:
        op.drop_column(_TABLA, "respuesta_texto", schema=_SCHEMA)
