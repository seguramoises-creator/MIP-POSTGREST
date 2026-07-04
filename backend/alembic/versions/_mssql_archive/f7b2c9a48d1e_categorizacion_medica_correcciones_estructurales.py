"""correcciones estructurales Categorizacion Medica (PENDIENTE, centro obligatorio, llave FACT)

Revision ID: f7b2c9a48d1e
Revises: 5f3a9c7e1b46
Create Date: 2026-06-21 00:00:00.000000

Tres correcciones detectadas al comparar la herramienta Excel real de
Categorizacion Medica contra el modelo de datos vigente:

1. Config.DIM_CategoriaMedica: score_min/score_max pasan de NOT NULL a
   NULLABLE, para soportar una nueva fila de catalogo 'PENDIENTE'
   (codigo='PENDIENTE', sin rango numerico). Antes, si los 5 criterios
   crudos de un medico venian vacios, calcular_score() devolvia
   score_total=0 y ese medico caia silenciosamente en categoria D (la mas
   baja) en vez de quedar marcado como "sin datos suficientes". Ver
   categorizacion_service.calcular_score() (ya actualizado para buscar
   esta fila antes de hacer fallback a 0).

2. Config.DIM_Medico: la restriccion UNIQUE(pais_id, nombre)
   ('UQ_Medico_Pais_Nombre') es insuficiente — nombres genericos de medico
   residente ("Residencia Medicina Interna", etc.) se repiten en centros
   medicos distintos y deberian poder distinguirse. Se cambia la identidad
   a (pais_id, nombre, centro_medico_id) ('UQ_Medico_Pais_Nombre_Centro'),
   lo que obliga a que centro_medico_id sea NOT NULL (en SQL Server un
   UNIQUE constraint trata multiples NULL como valores duplicados entre
   si, asi que dejarlo nullable dentro de esta llave rompe la unicidad
   real entre medicos sin centro capturado).

   Backfill: como la restriccion vieja ya garantizaba unicidad de
   (pais_id, nombre) por si sola, ninguna fila existente puede colisionar
   al agregar centro_medico_id a la llave. Solo se resuelve el NOT NULL:
   cualquier fila con centro_medico_id IS NULL se reasigna a un centro
   centinela "SIN CENTRO ASIGNADO" (creado si no existe ya) para el mismo
   pais_id, en vez de inventar un centro real o borrar el registro.

3. DW.FACT_CategorizacionMedica: la restriccion UNIQUE(medico_id, ciclo_id)
   ('UQ_CategorizacionMedica_Medico_Ciclo') no contempla que un mismo
   medico real puede ser visitado por mas de un RM/linea en el mismo ciclo
   (territorios/lineas superpuestos). Se cambia a
   (medico_id, rm_id, ciclo_id) ('UQ_CategorizacionMedica_Medico_RM_Ciclo').
   Como la restriccion vieja ya era unique sobre un subconjunto de estas
   columnas, ninguna fila existente puede violar la nueva (mas permisiva).
   Ver categorizacion_service.py (calcular_categorizacion_medico ya
   persiste por medico_id+rm_id+ciclo_id).

Modelos correspondientes ya actualizados:
  - app/models/dimensiones.py -> CategoriaMedica (score_min/score_max
    nullable), Medico (centro_medico_id NOT NULL, nuevo UniqueConstraint)
  - app/models/hechos.py -> CategorizacionMedica (nuevo UniqueConstraint)

NOTA sobre downgrade(): no revierte el backfill de centro_medico_id (no
hay forma segura de saber cuales filas eran originalmente NULL una vez
aplicado el upgrade), y recrear la restriccion vieja de
FACT_CategorizacionMedica puede fallar si ya existen filas con
medico_id+ciclo_id repetido por distinto rm_id capturadas despues del
upgrade — downgrade() es para revertir en el mismo despliegue, no para
usarse despues de cargar datos nuevos bajo el esquema nuevo.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f7b2c9a48d1e'
down_revision: Union[str, Sequence[str], None] = '5f3a9c7e1b46'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SENTINEL_CENTRO_NOMBRE = "SIN CENTRO ASIGNADO"


def upgrade() -> None:
    # ── 1) DIM_CategoriaMedica.score_min/score_max -> NULLABLE ──────────
    op.alter_column(
        'DIM_CategoriaMedica', 'score_min',
        existing_type=sa.Numeric(precision=6, scale=4),
        nullable=True, schema='Config',
    )
    op.alter_column(
        'DIM_CategoriaMedica', 'score_max',
        existing_type=sa.Numeric(precision=6, scale=4),
        nullable=True, schema='Config',
    )

    # Fila de catalogo 'PENDIENTE': sin rango numerico (score_min/max NULL),
    # representa "datos insuficientes para categorizar". orden=99 para que
    # quede al final de cualquier listado ordenado por A(1)-D(4).
    op.execute("""
        IF NOT EXISTS (SELECT 1 FROM [Config].[DIM_CategoriaMedica] WHERE codigo = 'PENDIENTE')
        INSERT INTO [Config].[DIM_CategoriaMedica]
            (codigo, nombre, descripcion, score_min, score_max, color_dashboard, orden, activo)
        VALUES (
            'PENDIENTE', 'Pendiente',
            'Datos insuficientes para categorizar (uno o mas de los 5 criterios sin capturar)',
            NULL, NULL, '#9E9E9E', 99, 1
        )
    """)

    # ── 2) DIM_Medico: centro_medico_id obligatorio + llave compuesta ───
    # 2a. Backfill: medicos sin centro -> centro centinela por pais.
    op.execute(f"""
        INSERT INTO [Config].[DIM_CentroMedico] (pais_id, nombre, activo)
        SELECT DISTINCT m.pais_id, '{SENTINEL_CENTRO_NOMBRE}', 1
        FROM [Config].[DIM_Medico] m
        WHERE m.centro_medico_id IS NULL
          AND NOT EXISTS (
              SELECT 1 FROM [Config].[DIM_CentroMedico] c
              WHERE c.pais_id = m.pais_id AND c.nombre = '{SENTINEL_CENTRO_NOMBRE}'
          )
    """)
    op.execute(f"""
        UPDATE m
        SET m.centro_medico_id = c.id
        FROM [Config].[DIM_Medico] m
        JOIN [Config].[DIM_CentroMedico] c
          ON c.pais_id = m.pais_id AND c.nombre = '{SENTINEL_CENTRO_NOMBRE}'
        WHERE m.centro_medico_id IS NULL
    """)

    # 2b. NOT NULL + swap de UNIQUE constraint.
    op.alter_column(
        'DIM_Medico', 'centro_medico_id',
        existing_type=sa.Integer(),
        nullable=False, schema='Config',
    )
    op.drop_constraint('UQ_Medico_Pais_Nombre', 'DIM_Medico', schema='Config', type_='unique')
    op.create_unique_constraint(
        'UQ_Medico_Pais_Nombre_Centro', 'DIM_Medico',
        ['pais_id', 'nombre', 'centro_medico_id'], schema='Config',
    )

    # ── 3) FACT_CategorizacionMedica: llave compuesta incluye rm_id ─────
    op.drop_constraint(
        'UQ_CategorizacionMedica_Medico_Ciclo', 'FACT_CategorizacionMedica',
        schema='DW', type_='unique',
    )
    op.create_unique_constraint(
        'UQ_CategorizacionMedica_Medico_RM_Ciclo', 'FACT_CategorizacionMedica',
        ['medico_id', 'rm_id', 'ciclo_id'], schema='DW',
    )


def downgrade() -> None:
    # ── 3) revertir FACT_CategorizacionMedica ────────────────────────────
    op.drop_constraint(
        'UQ_CategorizacionMedica_Medico_RM_Ciclo', 'FACT_CategorizacionMedica',
        schema='DW', type_='unique',
    )
    op.create_unique_constraint(
        'UQ_CategorizacionMedica_Medico_Ciclo', 'FACT_CategorizacionMedica',
        ['medico_id', 'ciclo_id'], schema='DW',
    )

    # ── 2) revertir DIM_Medico (no se revierte el backfill de centro) ───
    op.drop_constraint('UQ_Medico_Pais_Nombre_Centro', 'DIM_Medico', schema='Config', type_='unique')
    op.create_unique_constraint(
        'UQ_Medico_Pais_Nombre', 'DIM_Medico', ['pais_id', 'nombre'], schema='Config',
    )
    op.alter_column(
        'DIM_Medico', 'centro_medico_id',
        existing_type=sa.Integer(),
        nullable=True, schema='Config',
    )

    # ── 1) revertir DIM_CategoriaMedica ──────────────────────────────────
    op.execute("DELETE FROM [Config].[DIM_CategoriaMedica] WHERE codigo = 'PENDIENTE'")
    op.alter_column(
        'DIM_CategoriaMedica', 'score_max',
        existing_type=sa.Numeric(precision=6, scale=4),
        nullable=False, schema='Config',
    )
    op.alter_column(
        'DIM_CategoriaMedica', 'score_min',
        existing_type=sa.Numeric(precision=6, scale=4),
        nullable=False, schema='Config',
    )
