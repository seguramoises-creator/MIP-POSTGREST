"""Visita — DIM_MedicoVisita: flujo de aprobación de alta/baja (Gerente de Distrito)

Revision ID: e9f4b2c7a831
Revises: c7d2f4a8b615
Create Date: 2026-07-01

Aditiva e idempotente. Los médicos existentes quedan como APROBADO (grandfathered).
"""
from alembic import op
import sqlalchemy as sa

revision = "e9f4b2c7a831"
down_revision = "c7d2f4a8b615"
branch_labels = None
depends_on = None

_COLS = [
    ("estado_aprobacion", sa.String(length=16), "'APROBADO'"),
    ("ciclo_alta_id", sa.Integer(), None),
    ("ciclo_baja_id", sa.Integer(), None),
    ("solicitado_por", sa.Integer(), None),
    ("aprobado_por", sa.Integer(), None),
    ("fecha_solicitud", sa.DateTime(), None),
    ("fecha_aprobacion", sa.DateTime(), None),
    ("motivo", sa.String(length=300), None),
]


def _existing(insp) -> set:
    return {c["name"] for c in insp.get_columns("DIM_MedicoVisita", schema="Visita")}


def upgrade():
    insp = sa.inspect(op.get_bind())
    have = _existing(insp)
    for nombre, tipo, sdef in _COLS:
        if nombre not in have:
            kwargs = {"nullable": (nombre != "estado_aprobacion")}
            if sdef is not None:
                kwargs["server_default"] = sa.text(sdef)
            op.add_column("DIM_MedicoVisita", sa.Column(nombre, tipo, **kwargs), schema="Visita")
    # FKs a ciclo (best-effort; si el motor no las soporta inline, quedan como columnas).
    try:
        op.create_foreign_key("FK_MedicoVisita_ciclo_alta", "DIM_MedicoVisita", "DIM_Ciclo",
                              ["ciclo_alta_id"], ["id"], source_schema="Visita", referent_schema="Config")
        op.create_foreign_key("FK_MedicoVisita_ciclo_baja", "DIM_MedicoVisita", "DIM_Ciclo",
                              ["ciclo_baja_id"], ["id"], source_schema="Visita", referent_schema="Config")
    except Exception:
        pass


def downgrade():
    insp = sa.inspect(op.get_bind())
    have = _existing(insp)
    for nombre, _t, _s in reversed(_COLS):
        if nombre in have:
            op.drop_column("DIM_MedicoVisita", nombre, schema="Visita")
