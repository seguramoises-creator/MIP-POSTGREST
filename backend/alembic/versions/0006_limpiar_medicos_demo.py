"""Limpieza (una sola vez) de los médicos DEMO del Panel Médico y sus datos de visita.

El Panel arrancó con médicos de prueba ("ANA FLORES CRUZ", "DR. PEREZ GARCIA", etc.) que
traían especialidades genéricas. Tras unificar las dimensiones con las reales del Excel
(migración 0005), esos médicos demo distorsionaban el filtro de Especialidad. Esta migración
los elimina junto con sus dependencias (visitas, planeación, muestras) para dejar el Panel
limpio; el usuario cargará luego los médicos reales, que usarán las especialidades reales.

Se ejecuta una sola vez (Alembic la marca aplicada); los médicos reales que se agreguen
después NO se ven afectados.

Revision ID: 0006_limpiar_medicos_demo
Revises: 0005_sync_dims_maestras
"""
from alembic import op
import sqlalchemy as sa


revision = "0006_limpiar_medicos_demo"
down_revision = "0005_sync_dims_maestras"
branch_labels = None
depends_on = None

# Orden respetando las FKs (dependientes primero → maestro al final).
_TABLAS = [
    '"Visita"."MuestraEntregada"',
    '"Visita"."FactVisita"',
    '"Visita"."PlaneacionCiclo"',
    '"Visita"."DIM_MedicoVisita"',
]


def upgrade() -> None:
    conn = op.get_bind()
    for tabla in _TABLAS:
        conn.execute(sa.text(f"DELETE FROM {tabla}"))


def downgrade() -> None:
    # Los datos demo eliminados no se pueden restaurar (eran de prueba). No-op.
    pass
