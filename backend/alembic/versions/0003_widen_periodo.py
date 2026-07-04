"""Ensanchar cat.*.Periodo de VARCHAR(7) a VARCHAR(20).

El baseline creó cat.LoadBatch.Periodo y cat.FactMedicoCategoriaSnapshot.Periodo
como String(7), pero el formato real de período es el código de ciclo (p. ej.
'C03-2026', 8 chars) — en SQL Server la columna es VARCHAR(20). Se alinea el
ancho para no truncar los datos reales.

La vista cat.vwMedicoCategoriaConciliacion depende de Snapshot.Periodo, así que
se suelta antes de alterar y se recrea igual que en la migración 0002.

Revision ID: 0003_widen_periodo
Revises: 0002_views_postgres
Create Date: 2026-07-04
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_widen_periodo"
down_revision = "0002_views_postgres"
branch_labels = None
depends_on = None

_TABLAS = [("cat", "LoadBatch"), ("cat", "FactMedicoCategoriaSnapshot")]

# Idéntica a la de la migración 0002 (la vista se recrea tras el ALTER).
_VW_CONCILIACION = '''
CREATE VIEW "cat"."vwMedicoCategoriaConciliacion" AS
SELECT
    f."Periodo",
    p."CodigoPais",
    r."CodigoRepresentante",
    r."NombreRepresentante",
    m."NombreMedico",
    e."Especialidad",
    f."Equipo",
    f."LineaIdOrigen",
    ROUND(f."PuntajeTotalPct" * 100, 2) AS "PuntajeTotalPct",
    f."CategoriaCalculada",
    f."CategoriaExcel",
    CASE
        WHEN f."CategoriaExcel" IS NULL THEN 'SIN_CATEGORIA_EXCEL'
        WHEN f."CategoriaCalculada" = f."CategoriaExcel" THEN 'OK'
        ELSE 'DIFERENCIA'
    END AS "EstadoConciliacion",
    f."EstadoCalculo",
    f."MensajeCalculo",
    f."LoadBatchKey",
    f."MedicoCategoriaKey"
FROM "cat"."FactMedicoCategoriaSnapshot" f
JOIN "cat"."DimPais" p ON p."PaisKey" = f."PaisKey"
JOIN "cat"."DimMedico" m ON m."MedicoKey" = f."MedicoKey"
LEFT JOIN "cat"."DimEspecialidad" e ON e."EspecialidadKey" = m."EspecialidadKey"
LEFT JOIN "cat"."DimRepresentanteMedico" r ON r."RepresentanteKey" = f."RepresentanteKey"
'''


def upgrade():
    op.execute('DROP VIEW IF EXISTS "cat"."vwMedicoCategoriaConciliacion"')
    for schema, tabla in _TABLAS:
        op.alter_column(tabla, "Periodo", schema=schema,
                        type_=sa.String(20), existing_nullable=False)
    op.execute(_VW_CONCILIACION)


def downgrade():
    op.execute('DROP VIEW IF EXISTS "cat"."vwMedicoCategoriaConciliacion"')
    for schema, tabla in _TABLAS:
        op.alter_column(tabla, "Periodo", schema=schema,
                        type_=sa.String(7), existing_nullable=False)
    op.execute(_VW_CONCILIACION)
