"""Vistas PostgreSQL de los esquemas cat.* (traducidas de T-SQL).

El baseline crea tablas ORM + las 6 tablas cat/stg sin modelo, pero NO las
VISTAS que la edición SQL Server creaba en sus migraciones. Esta migración las
reproduce en sintaxis Postgres:

  - cat.vwMedicoCategoriaConciliacion  (categorización — get_resultados)
  - cat.vwDashboardCoberturaPredictivaGD (cobertura — get_dashboard_cat)

Traducción T-SQL→Postgres: identificadores mixed-case entre comillas dobles,
ISNULL→COALESCE, CAST(... AS DECIMAL(p,s))→NUMERIC(p,s), sin escape de EXEC.

Revision ID: 0002_views_postgres
Revises: 0001_baseline_postgres
Create Date: 2026-07-04
"""
from alembic import op

revision = "0002_views_postgres"
down_revision = "0001_baseline_postgres"
branch_labels = None
depends_on = None


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

_VW_DASHBOARD = '''
CREATE VIEW "cat"."vwDashboardCoberturaPredictivaGD" AS
SELECT
    k."KpiKey",
    k."FechaCorte",
    p."CodigoPais",
    p."NombrePais",
    c."CodigoCiclo",
    c."FechaInicio" AS "CicloFechaInicio",
    c."FechaFin"    AS "CicloFechaFin",
    COALESCE(k."Linea", r."EquipoTexto") AS "Linea",
    k."GD",
    r."CodigoRepresentante",
    r."NombreRepresentante",
    r."EquipoTexto",
    k."MedicosProgramados",
    k."MedicosVisitadosUnicos",
    CAST(k."CoberturaActualPct"     * 100 AS NUMERIC(9,2)) AS "CoberturaActualPct",
    CAST(k."CoberturaEsperadaPct"   * 100 AS NUMERIC(9,2)) AS "CoberturaEsperadaPct",
    CAST(k."CoberturaProyectadaPct" * 100 AS NUMERIC(9,2)) AS "CoberturaProyectadaPct",
    CAST(k."MetaCoberturaPct"       * 100 AS NUMERIC(9,2)) AS "MetaCoberturaPct",
    CAST(k."BrechaActualVsEsperada" * 100 AS NUMERIC(9,2)) AS "BrechaActualVsEsperadaPct",
    CAST(k."BrechaProyectadaVsMeta" * 100 AS NUMERIC(9,2)) AS "BrechaProyectadaVsMetaPct",
    k."MedicosRequeridosMeta",
    k."MedicosPendientesMeta",
    k."MedicosDiariosRequeridos",
    k."ContactosMetaCiclo",
    k."ContactosRealizados",
    CAST(k."CumplimientoContactosPct" * 100 AS NUMERIC(9,2)) AS "CumplimientoContactosPct",
    CAST(k."ContactosProyectados" AS NUMERIC(12,1))         AS "ContactosProyectados",
    CAST(k."ContactosPendientes"  AS NUMERIC(12,1))         AS "ContactosPendientes",
    k."ContactosDiariosRequeridos",
    k."DiasHabilesTotales",
    k."DiasHabilesTranscurridos",
    k."DiasHabilesRestantes",
    k."EstadoCobertura",
    k."EstadoRitmo",
    k."EstadoPSP",
    k."LecturaAccionable",
    k."FechaCargaUtc"
FROM "cat"."KpiCoberturaPredictiva" k
INNER JOIN "cat"."DimCiclo"               c ON c."CicloKey"        = k."CicloKey"
INNER JOIN "cat"."DimPais"                p ON p."PaisKey"         = k."PaisKey"
INNER JOIN "cat"."DimRepresentanteMedico" r ON r."RepresentanteKey" = k."RepresentanteKey"
'''


def upgrade():
    op.execute('DROP VIEW IF EXISTS "cat"."vwMedicoCategoriaConciliacion"')
    op.execute(_VW_CONCILIACION)
    op.execute('DROP VIEW IF EXISTS "cat"."vwDashboardCoberturaPredictivaGD"')
    op.execute(_VW_DASHBOARD)


def downgrade():
    op.execute('DROP VIEW IF EXISTS "cat"."vwDashboardCoberturaPredictivaGD"')
    op.execute('DROP VIEW IF EXISTS "cat"."vwMedicoCategoriaConciliacion"')
