"""agregar tablas Modulo Cobertura Predictiva y Ritmo de Ejecucion (4DX)

Revision ID: e8a1d4f7c2b6
Revises: d6f9c1a4e7b3
Create Date: 2026-06-19 00:00:00.000000

NUEVO MODULO: Cobertura Predictiva y Ritmo de Ejecucion (metodologia 4DX).

Sustituye en el dashboard de GD las metricas de Comercial / Ventas, EVO IR
y cumplimiento de cuota (lag measures) por metricas predictivas de cobertura
medica (lead measures), replicando el motor de calculo del Excel de
referencia "Modulo_Cobertura_Predictiva_Ejemplo_VM_v3.xlsx" (hoja
Motor_Formulas).

Se crean 4 tablas nuevas:

  - Config.DIM_TargetMedico: universo de medicos asignados a cada RM por
    ciclo (origen: hoja Target_Medicos). Alimenta el calculo de medicos
    programados (J) y medicos requeridos por meta (K).
  - Config.DIM_Feriado: catalogo de feriados por pais, reemplaza el rango
    estatico Parametros!$B$17:$B$25 del Excel. Alimenta NETWORKDAYS para
    dias habiles (columnas N/O/P) cuando Config.DIM_Ciclo.dias_laborables
    no esta configurado (=0).
  - Config.DIM_ParametroCobertura: meta de cobertura parametrizable por
    pais/linea/ciclo (resolucion en cascada), reemplaza el valor global
    fijo Parametros!$B$4. Atiende la nota "Nota Moises: Debe quedar
    parametrizable por linea/ciclo" de la hoja Diccionario.
  - DW.FACT_Visita: bitacora de visitas (origen: hoja Fact_Visitas).
    Alimenta medicos unicos visitados (L, via DISTINCT medico_codigo) y
    contactos realizados (M, via COUNT total), ambos filtrados por
    estado_visita='Realizada' y fecha_visita <= fecha de corte.

Tambien se agrega la columna `gerente_id` a Security.DIM_Usuario, para
auto-filtrar a los usuarios con rol GERENTE_DISTRITO a su propio equipo de
RMs en los nuevos endpoints (mismo patron ya usado por `rm_id`).

Modelos correspondientes:
  - app/models/dimensiones.py -> TargetMedico, Feriado, ParametroCobertura
  - app/models/hechos.py -> Visita
  - app/models/usuario.py -> Usuario.gerente_id
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e8a1d4f7c2b6'
down_revision: Union[str, Sequence[str], None] = 'd6f9c1a4e7b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1) Config.DIM_TargetMedico ──────────────────────────────────────
    op.create_table(
        'DIM_TargetMedico',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('pais_id', sa.Integer(), nullable=False),
        sa.Column('rm_id', sa.Integer(), nullable=False),
        sa.Column('ciclo_id', sa.Integer(), nullable=False),
        sa.Column('medico_codigo', sa.String(length=50), nullable=False),
        sa.Column('medico_nombre', sa.String(length=200), nullable=True),
        sa.Column('especialidad', sa.String(length=100), nullable=True),
        sa.Column('potencial', sa.String(length=20), nullable=True),
        sa.Column('programado', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('activo', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(['pais_id'], ['Config.DIM_Pais.id'], ),
        sa.ForeignKeyConstraint(['rm_id'], ['Config.DIM_RM.id'], ),
        sa.ForeignKeyConstraint(['ciclo_id'], ['Config.DIM_Ciclo.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('rm_id', 'ciclo_id', 'medico_codigo', name='UQ_TargetMedico_RM_Ciclo_Medico'),
        schema='Config',
    )
    op.create_index(op.f('ix_Config_DIM_TargetMedico_pais_id'), 'DIM_TargetMedico', ['pais_id'], unique=False, schema='Config')
    op.create_index(op.f('ix_Config_DIM_TargetMedico_rm_id'), 'DIM_TargetMedico', ['rm_id'], unique=False, schema='Config')
    op.create_index(op.f('ix_Config_DIM_TargetMedico_ciclo_id'), 'DIM_TargetMedico', ['ciclo_id'], unique=False, schema='Config')

    # ── 2) Config.DIM_Feriado ────────────────────────────────────────────
    op.create_table(
        'DIM_Feriado',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('pais_id', sa.Integer(), nullable=False),
        sa.Column('fecha', sa.Date(), nullable=False),
        sa.Column('nombre', sa.String(length=150), nullable=True),
        sa.Column('activo', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(['pais_id'], ['Config.DIM_Pais.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('pais_id', 'fecha', name='UQ_Feriado_Pais_Fecha'),
        schema='Config',
    )
    op.create_index(op.f('ix_Config_DIM_Feriado_pais_id'), 'DIM_Feriado', ['pais_id'], unique=False, schema='Config')
    op.create_index(op.f('ix_Config_DIM_Feriado_fecha'), 'DIM_Feriado', ['fecha'], unique=False, schema='Config')

    # ── 3) Config.DIM_ParametroCobertura ─────────────────────────────────
    op.create_table(
        'DIM_ParametroCobertura',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('pais_id', sa.Integer(), nullable=False),
        sa.Column('linea_id', sa.Integer(), nullable=True),
        sa.Column('ciclo_id', sa.Integer(), nullable=True),
        sa.Column('meta_cobertura', sa.Numeric(precision=5, scale=4), nullable=False, server_default='0.90'),
        sa.Column('activo', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(['pais_id'], ['Config.DIM_Pais.id'], ),
        sa.ForeignKeyConstraint(['linea_id'], ['Config.DIM_Linea.id'], ),
        sa.ForeignKeyConstraint(['ciclo_id'], ['Config.DIM_Ciclo.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('pais_id', 'linea_id', 'ciclo_id', name='UQ_ParametroCobertura_Pais_Linea_Ciclo'),
        schema='Config',
    )
    op.create_index(op.f('ix_Config_DIM_ParametroCobertura_pais_id'), 'DIM_ParametroCobertura', ['pais_id'], unique=False, schema='Config')

    # ── 4) DW.FACT_Visita ─────────────────────────────────────────────────
    op.create_table(
        'FACT_Visita',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('pais_id', sa.Integer(), nullable=False),
        sa.Column('rm_id', sa.Integer(), nullable=False),
        sa.Column('ciclo_id', sa.Integer(), nullable=False),
        sa.Column('medico_codigo', sa.String(length=50), nullable=False),
        sa.Column('fecha_visita', sa.Date(), nullable=False),
        sa.Column('tipo_contacto', sa.String(length=50), nullable=True),
        sa.Column('estado_visita', sa.String(length=20), nullable=False, server_default='Realizada'),
        sa.Column('producto_foco', sa.String(length=100), nullable=True),
        sa.Column('carga_excel_id', sa.Integer(), nullable=True),
        sa.Column('fecha_carga', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['pais_id'], ['Config.DIM_Pais.id'], ),
        sa.ForeignKeyConstraint(['rm_id'], ['Config.DIM_RM.id'], ),
        sa.ForeignKeyConstraint(['ciclo_id'], ['Config.DIM_Ciclo.id'], ),
        sa.PrimaryKeyConstraint('id'),
        schema='DW',
    )
    op.create_index(op.f('ix_DW_FACT_Visita_pais_id'), 'FACT_Visita', ['pais_id'], unique=False, schema='DW')
    op.create_index(op.f('ix_DW_FACT_Visita_rm_id'), 'FACT_Visita', ['rm_id'], unique=False, schema='DW')
    op.create_index(op.f('ix_DW_FACT_Visita_ciclo_id'), 'FACT_Visita', ['ciclo_id'], unique=False, schema='DW')
    op.create_index(op.f('ix_DW_FACT_Visita_medico_codigo'), 'FACT_Visita', ['medico_codigo'], unique=False, schema='DW')
    op.create_index(op.f('ix_DW_FACT_Visita_fecha_visita'), 'FACT_Visita', ['fecha_visita'], unique=False, schema='DW')

    # ── 5) Security.DIM_Usuario.gerente_id (auto-filtro GD) ──────────────
    op.add_column('DIM_Usuario', sa.Column('gerente_id', sa.Integer(), nullable=True), schema='Security')


def downgrade() -> None:
    op.drop_column('DIM_Usuario', 'gerente_id', schema='Security')

    op.drop_index(op.f('ix_DW_FACT_Visita_fecha_visita'), table_name='FACT_Visita', schema='DW')
    op.drop_index(op.f('ix_DW_FACT_Visita_medico_codigo'), table_name='FACT_Visita', schema='DW')
    op.drop_index(op.f('ix_DW_FACT_Visita_ciclo_id'), table_name='FACT_Visita', schema='DW')
    op.drop_index(op.f('ix_DW_FACT_Visita_rm_id'), table_name='FACT_Visita', schema='DW')
    op.drop_index(op.f('ix_DW_FACT_Visita_pais_id'), table_name='FACT_Visita', schema='DW')
    op.drop_table('FACT_Visita', schema='DW')

    op.drop_index(op.f('ix_Config_DIM_ParametroCobertura_pais_id'), table_name='DIM_ParametroCobertura', schema='Config')
    op.drop_table('DIM_ParametroCobertura', schema='Config')

    op.drop_index(op.f('ix_Config_DIM_Feriado_fecha'), table_name='DIM_Feriado', schema='Config')
    op.drop_index(op.f('ix_Config_DIM_Feriado_pais_id'), table_name='DIM_Feriado', schema='Config')
    op.drop_table('DIM_Feriado', schema='Config')

    op.drop_index(op.f('ix_Config_DIM_TargetMedico_ciclo_id'), table_name='DIM_TargetMedico', schema='Config')
    op.drop_index(op.f('ix_Config_DIM_TargetMedico_rm_id'), table_name='DIM_TargetMedico', schema='Config')
    op.drop_index(op.f('ix_Config_DIM_TargetMedico_pais_id'), table_name='DIM_TargetMedico', schema='Config')
    op.drop_table('DIM_TargetMedico', schema='Config')
