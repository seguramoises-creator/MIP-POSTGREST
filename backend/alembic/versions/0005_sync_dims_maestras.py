"""Unificación de dimensiones: poblar Config.DIM_* (fuente única del sistema) con las
especialidades / provincias / municipios / centros reales ya cargados en cat.* (Excel de
Categorización), y desactivar las especialidades genéricas que no vienen del negocio.

Idempotente y defensivo:
- Los INSERT son insert-if-not-exists (no duplican; re-ejecutable).
- La desactivación de especialidades genéricas SOLO ocurre si cat.DimEspecialidad tiene
  filas (si está vacío — BD nueva sin carga — no se toca nada, para no dejar el catálogo sin
  especialidades).

Revision ID: 0005_sync_dims_maestras
Revises: 0004_seed_provincias_rd
"""
from alembic import op
import sqlalchemy as sa


revision = "0005_sync_dims_maestras"
down_revision = "0004_seed_provincias_rd"
branch_labels = None
depends_on = None


_SYNC_ESPECIALIDAD = """
INSERT INTO "Config"."DIM_Especialidad" (nombre, activo)
SELECT DISTINCT TRIM(e."Especialidad"), TRUE FROM "cat"."DimEspecialidad" e
WHERE e."Especialidad" IS NOT NULL AND TRIM(e."Especialidad") <> ''
  AND NOT EXISTS (SELECT 1 FROM "Config"."DIM_Especialidad" d WHERE LOWER(d.nombre)=LOWER(TRIM(e."Especialidad")))
"""
_SYNC_PROVINCIA = """
INSERT INTO "Config"."DIM_Provincia" (pais_codigo, nombre, activo)
SELECT DISTINCT pa."CodigoPais", TRIM(g."Provincia"), TRUE
FROM "cat"."DimGeografia" g JOIN "cat"."DimPais" pa ON pa."PaisKey"=g."PaisKey"
WHERE g."Provincia" IS NOT NULL AND TRIM(g."Provincia") <> ''
  AND EXISTS (SELECT 1 FROM "Config"."DIM_Pais" cp WHERE cp.codigo=pa."CodigoPais")
  AND NOT EXISTS (SELECT 1 FROM "Config"."DIM_Provincia" d WHERE d.pais_codigo=pa."CodigoPais" AND LOWER(d.nombre)=LOWER(TRIM(g."Provincia")))
"""
_SYNC_MUNICIPIO = """
INSERT INTO "Config"."DIM_Municipio" (provincia_id, nombre, activo)
SELECT DISTINCT pr.id, TRIM(g."Municipio"), TRUE
FROM "cat"."DimGeografia" g JOIN "cat"."DimPais" pa ON pa."PaisKey"=g."PaisKey"
JOIN "Config"."DIM_Provincia" pr ON pr.pais_codigo=pa."CodigoPais" AND LOWER(pr.nombre)=LOWER(TRIM(g."Provincia"))
WHERE g."Municipio" IS NOT NULL AND TRIM(g."Municipio") <> ''
  AND NOT EXISTS (SELECT 1 FROM "Config"."DIM_Municipio" d WHERE d.provincia_id=pr.id AND LOWER(d.nombre)=LOWER(TRIM(g."Municipio")))
"""
_SYNC_CENTRO = """
INSERT INTO "Config"."DIM_CentroMedico" (pais_codigo, nombre, activo)
SELECT DISTINCT pa."CodigoPais", TRIM(c."CentroMedico"), TRUE
FROM "cat"."DimCentroMedico" c JOIN "cat"."DimPais" pa ON pa."PaisKey"=c."PaisKey"
WHERE c."CentroMedico" IS NOT NULL AND TRIM(c."CentroMedico") <> ''
  AND EXISTS (SELECT 1 FROM "Config"."DIM_Pais" cp WHERE cp.codigo=pa."CodigoPais")
  AND NOT EXISTS (SELECT 1 FROM "Config"."DIM_CentroMedico" d WHERE d.pais_codigo=pa."CodigoPais" AND d.nombre=TRIM(c."CentroMedico"))
"""
_DESACTIVAR_GENERICAS = """
UPDATE "Config"."DIM_Especialidad" SET activo=FALSE
WHERE LOWER(nombre) NOT IN (SELECT LOWER(TRIM("Especialidad")) FROM "cat"."DimEspecialidad")
"""


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text(_SYNC_ESPECIALIDAD))
    conn.execute(sa.text(_SYNC_PROVINCIA))
    conn.execute(sa.text(_SYNC_MUNICIPIO))
    conn.execute(sa.text(_SYNC_CENTRO))
    # Reemplazo de especialidades: desactivar las genéricas solo si hay especialidades reales cargadas.
    hay_reales = conn.execute(sa.text('SELECT COUNT(*) FROM "cat"."DimEspecialidad"')).scalar()
    if hay_reales:
        conn.execute(sa.text(_DESACTIVAR_GENERICAS))


def downgrade() -> None:
    # Reactivar todas las especialidades (no se puede saber cuáles estaban desactivadas antes).
    # Los datos insertados en Config.DIM_* se conservan (no se borran en la baja).
    op.get_bind().execute(sa.text('UPDATE "Config"."DIM_Especialidad" SET activo=TRUE'))
