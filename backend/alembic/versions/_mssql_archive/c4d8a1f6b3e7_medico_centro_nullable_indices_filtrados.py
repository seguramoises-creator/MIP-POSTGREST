"""DIM_Medico: centro_medico_id nullable + indices unicos filtrados (universo dual Categorizacion/Cobertura)

Revision ID: c4d8a1f6b3e7
Revises: f7b2c9a48d1e
Create Date: 2026-06-22 00:00:00.000000

Fusion decidida jun-2026 (ver dims.py, hoja DIM_MEDICOCOBERTURA): la misma
tabla Config.DIM_Medico ahora sirve a DOS universos medicos distintos:

1) Categorizacion Medica (Excel propio, sin codigo estable): identidad por
   (pais_id, nombre, centro_medico_id) -- centro obligatorio en este flujo
   (ver categorizacion_service.resolver_medico(), sin cambios).

2) Cobertura Predictiva/4DX, hoja DIM_MEDICOCOBERTURA: SI trae un codigo de
   medico estable (MEDICO_ID -> columna `codigo`, ya existente desde
   a7c3f9e1b4d6). Identidad por (pais_id, codigo); no captura centro medico
   -> centro_medico_id queda NULL para estas filas. Ver
   categorizacion_service.resolver_medico_por_codigo() (nueva).

Por eso centro_medico_id vuelve a ser NULLABLE (lo opuesto de lo que hizo
f7b2c9a48d1e, que lo puso NOT NULL para el universo de Categorizacion
unicamente -- en ese momento no se conocia el universo de Cobertura
compartiendo la tabla). La UNIQUE constraint simple
'UQ_Medico_Pais_Nombre_Centro' (pais_id, nombre, centro_medico_id) se
reemplaza por DOS INDICES UNICOS FILTRADOS, porque en SQL Server una
UNIQUE constraint/indice normal trata multiples NULL como duplicados (solo
permite UNA fila con NULL en la columna), lo cual rompe cualquiera de los
dos universos si comparten un solo indice sin filtro:

  - UQ_Medico_Pais_Codigo        ON (pais_id, codigo) WHERE codigo IS NOT NULL
  - UQ_Medico_Pais_Nombre_Centro ON (pais_id, nombre, centro_medico_id) WHERE codigo IS NULL

Los indices filtrados excluyen las filas que no aplican a cada universo,
evitando el problema de "multiples NULL" por completo. Ningun backfill es
necesario en upgrade(): relajar NOT NULL -> NULLABLE no afecta filas
existentes, y el filtro 'WHERE codigo IS NULL' del segundo indice cubre
exactamente el mismo subconjunto de filas (todas, hoy) que ya satisfacia la
constraint vieja -- no puede haber colision nueva.

Modelo correspondiente ya actualizado: app/models/dimensiones.py -> Medico
(centro_medico_id nullable=True, Index(..., mssql_where=...) x2 en vez de
UniqueConstraint). Sin cambios en hechos.py ni en categorizacion_service.py
mas alla de la nueva funcion resolver_medico_por_codigo() (ya en disco).

NOTA sobre downgrade(): revertir a NOT NULL requiere backfill de las filas
codigo-based (centro_medico_id IS NULL) hacia el mismo centro centinela
"SIN CENTRO ASIGNADO" usado por f7b2c9a48d1e. Si para ese momento ya existen
medicos de Cobertura con el mismo (pais_id, nombre) que algun medico de
Categorizacion ya asignado a ese centro centinela, recrear la UNIQUE
constraint simple puede fallar por colision real de nombre+centro -- este
downgrade es para revertir en el mismo despliegue (universo de Cobertura
aun vacio), no para usarse despues de cargar DIM_MEDICOCOBERTURA en
produccion.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4d8a1f6b3e7'
down_revision: Union[str, Sequence[str], None] = 'f7b2c9a48d1e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SENTINEL_CENTRO_NOMBRE = "SIN CENTRO ASIGNADO"


def upgrade() -> None:
    # 1) Quitar la UNIQUE constraint simple (bloquearia crear los indices
    #    filtrados sobre las mismas columnas).
    op.drop_constraint('UQ_Medico_Pais_Nombre_Centro', 'DIM_Medico', schema='Config', type_='unique')

    # 2) centro_medico_id NOT NULL -> NULLABLE (sin backfill, no hay perdida
    #    de datos posible al relajar la restriccion).
    op.alter_column(
        'DIM_Medico', 'centro_medico_id',
        existing_type=sa.Integer(),
        nullable=True, schema='Config',
    )

    # 3) Dos indices unicos filtrados en vez de una sola UNIQUE constraint.
    op.create_index(
        'UQ_Medico_Pais_Codigo', 'DIM_Medico', ['pais_id', 'codigo'],
        unique=True, schema='Config',
        mssql_where=sa.text('codigo IS NOT NULL'),
    )
    op.create_index(
        'UQ_Medico_Pais_Nombre_Centro', 'DIM_Medico', ['pais_id', 'nombre', 'centro_medico_id'],
        unique=True, schema='Config',
        mssql_where=sa.text('codigo IS NULL'),
    )


def downgrade() -> None:
    # ── revertir 3) ───────────────────────────────────────────────────────
    op.drop_index('UQ_Medico_Pais_Nombre_Centro', table_name='DIM_Medico', schema='Config')
    op.drop_index('UQ_Medico_Pais_Codigo', table_name='DIM_Medico', schema='Config')

    # ── revertir 2) — backfill primero (ver NOTA de modulo) ─────────────
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
    op.alter_column(
        'DIM_Medico', 'centro_medico_id',
        existing_type=sa.Integer(),
        nullable=False, schema='Config',
    )

    # ── revertir 1) ───────────────────────────────────────────────────────
    op.create_unique_constraint(
        'UQ_Medico_Pais_Nombre_Centro', 'DIM_Medico',
        ['pais_id', 'nombre', 'centro_medico_id'], schema='Config',
    )
