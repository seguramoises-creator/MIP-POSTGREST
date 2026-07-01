"""Visita — DIM_MedicoVisita: campos ampliados (identificación, ubicación, contacto,
consulta, comercial) para el Panel Médico

Revision ID: c7d2f4a8b615
Revises: a1e6c8f4b273
Create Date: 2026-07-01

Aditiva e idempotente: agrega columnas nullable, no toca datos existentes.
"""
from alembic import op
import sqlalchemy as sa

revision = "c7d2f4a8b615"
down_revision = "a1e6c8f4b273"
branch_labels = None
depends_on = None

# (columna, tipo) — todas nullable; los booleanos con server_default.
_COLS = [
    ("codigo", sa.String(length=40), None),
    ("nombre", sa.String(length=100), None),
    ("apellidos", sa.String(length=150), None),
    ("subespecialidad", sa.String(length=120), None),
    ("centro_trabajo", sa.String(length=200), None),
    ("institucion_tipo", sa.String(length=20), None),
    ("provincia", sa.String(length=100), None),
    ("municipio", sa.String(length=100), None),
    ("sector", sa.String(length=100), None),
    ("latitud", sa.Numeric(10, 7), None),
    ("longitud", sa.Numeric(10, 7), None),
    ("email", sa.String(length=200), None),
    ("exequatur", sa.String(length=50), None),
    ("dias_consulta", sa.String(length=100), None),
    ("horario_consulta", sa.String(length=100), None),
    ("frecuencia_visita", sa.String(length=20), None),
    ("acepta_visita", sa.Boolean(), "1"),
    ("potencial_prescripcion", sa.String(length=20), None),
    ("kol", sa.Boolean(), "0"),
    ("segmento", sa.String(length=60), None),
    ("observaciones", sa.String(length=500), None),
    ("fecha_alta", sa.Date(), None),
]


def _existing(insp) -> set:
    return {c["name"] for c in insp.get_columns("DIM_MedicoVisita", schema="Visita")}


def upgrade():
    insp = sa.inspect(op.get_bind())
    have = _existing(insp)
    for nombre, tipo, sdef in _COLS:
        if nombre not in have:
            kwargs = {"nullable": True}
            if sdef is not None:
                kwargs["server_default"] = sa.text(sdef)
            op.add_column("DIM_MedicoVisita", sa.Column(nombre, tipo, **kwargs), schema="Visita")


def downgrade():
    insp = sa.inspect(op.get_bind())
    have = _existing(insp)
    for nombre, _tipo, _sdef in reversed(_COLS):
        if nombre in have:
            op.drop_column("DIM_MedicoVisita", nombre, schema="Visita")
