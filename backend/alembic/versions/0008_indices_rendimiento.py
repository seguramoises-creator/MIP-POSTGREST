"""Índices de rendimiento: búsqueda de médico (trigram) y ruptura de visita.

Optimización PG (no cambia esquema de datos, solo acelera lecturas):
- `ix_dimmedico_nombre_trgm`: índice GIN trigram sobre LOWER("NombreMedico") de
  cat.DimMedico. Acelera la búsqueda de médico por nombre (`LOWER(...) LIKE '%x%'`),
  que sin él hace seq scan. Escala con el universo de médicos entre países.
- `ix_medicovisita_ciclos_sin_visita`: B-tree sobre Visita.DIM_MedicoVisita.
  ciclos_sin_visita. Acelera Ruptura/Cierre (filtro `ciclos_sin_visita >= N` sobre
  todo el panel).

Costo de escritura despreciable (médicos y panel se insertan rara vez).

Revision ID: 0008_indices_rendimiento
Revises: 0007_modulo_coaching_more
"""
from alembic import op

revision = "0008_indices_rendimiento"
down_revision = "0007_modulo_coaching_more"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        'CREATE INDEX IF NOT EXISTS ix_dimmedico_nombre_trgm '
        'ON "cat"."DimMedico" USING gin (LOWER("NombreMedico") gin_trgm_ops)'
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS ix_medicovisita_ciclos_sin_visita '
        'ON "Visita"."DIM_MedicoVisita" (ciclos_sin_visita)'
    )


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS "Visita"."ix_medicovisita_ciclos_sin_visita"')
    op.execute('DROP INDEX IF EXISTS "cat"."ix_dimmedico_nombre_trgm"')
