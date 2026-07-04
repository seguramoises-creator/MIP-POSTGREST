"""agregar tablas Modulo Categorizacion Medica (sustituye a Capacitacion)

Revision ID: a7c3f9e1b4d6
Revises: e8a1d4f7c2b6
Create Date: 2026-06-21 00:00:00.000000

NUEVO MODULO: Categorizacion Medica.

Sustituye en el menu/router al modulo de Capacitacion (ver capacitacion.py /
Capacitacion.tsx, que quedan en disco pero deja de registrarse, mismo patron
ya usado para reemplazar Comercial por Cobertura Predictiva). Clasifica cada
medico del universo objetivo en una categoria A/B/C/D segun un score
ponderado de 5 criterios, replicando el motor de calculo de la "Plantilla
Calculo de Categorias BFD(OCT) usar este maximo.xlsx" (hoja Bases y
Criterios / Calculos).

Reutiliza entidades ya existentes en vez de duplicarlas:
  - "Distrito"/"Equipo" del Excel de origen -> Config.DIM_Gerente (tipo=DISTRITO)
  - "Representante" del Excel de origen      -> Config.DIM_RM
Por eso NO se crean DIM_Distrito ni DIM_Representante.

Se crean 9 tablas nuevas:

  - Config.DIM_Especialidad: catalogo global de especialidades medicas.
  - Config.DIM_Provincia: provincias por pais.
  - Config.DIM_Municipio: municipios, hijos de Provincia.
  - Config.DIM_CentroMedico: centros medicos / clinicas / consultorios.
  - Config.DIM_CategoriaMedica: categorias A/B/C/D parametrizables
    (codigo/nombre/rango score_min-score_max/color), mismo patron que
    DIM_CategoriaDesempeno.
  - Config.DIM_CriterioCategoria: los 5 criterios ponderados del motor
    (Pacientes/Semana 30%, Poder Adquisitivo 20%, Potencial de Prescripcion
    10%, Ubicacion Territorial 30%, KOL 10%).
  - Config.DIM_CriterioCategoriaTabla: tabla unificada de niveles 1-5 por
    criterio (rango numerico O etiqueta), parametrizada opcionalmente por
    pais (solo Poder Adquisitivo/Costo de Consulta varia por pais en el
    Excel de origen).
  - Config.DIM_Medico: primera dimension medica real de MSM (Cobertura
    Predictiva solo usa un medico_codigo libre, sin catalogo propio).
  - DW.FACT_CategorizacionMedica: una fila por (medico_id, ciclo_id) con los
    valores capturados, niveles, scores ponderados, score_total, categoria
    actual y categoria_anterior_id (historial, mismo patron que
    FACT_RankingRM.posicion_anterior).

Modelos correspondientes:
  - app/models/dimensiones.py -> Especialidad, Provincia, Municipio,
    CentroMedico, CategoriaMedica, CriterioCategoria, CriterioCategoriaTabla,
    Medico
  - app/models/hechos.py -> CategorizacionMedica
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7c3f9e1b4d6'
down_revision: Union[str, Sequence[str], None] = 'e8a1d4f7c2b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1) Config.DIM_Especialidad ──────────────────────────────────────
    op.create_table(
        'DIM_Especialidad',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('nombre', sa.String(length=150), nullable=False),
        sa.Column('activo', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('nombre', name='UQ_Especialidad_Nombre'),
        schema='Config',
    )

    # ── 2) Config.DIM_Provincia ──────────────────────────────────────────
    op.create_table(
        'DIM_Provincia',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('pais_id', sa.Integer(), nullable=False),
        sa.Column('nombre', sa.String(length=150), nullable=False),
        sa.Column('activo', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(['pais_id'], ['Config.DIM_Pais.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('pais_id', 'nombre', name='UQ_Provincia_Pais_Nombre'),
        schema='Config',
    )
    op.create_index(op.f('ix_Config_DIM_Provincia_pais_id'), 'DIM_Provincia', ['pais_id'], unique=False, schema='Config')

    # ── 3) Config.DIM_Municipio ──────────────────────────────────────────
    op.create_table(
        'DIM_Municipio',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('provincia_id', sa.Integer(), nullable=False),
        sa.Column('nombre', sa.String(length=150), nullable=False),
        sa.Column('activo', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(['provincia_id'], ['Config.DIM_Provincia.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('provincia_id', 'nombre', name='UQ_Municipio_Provincia_Nombre'),
        schema='Config',
    )
    op.create_index(op.f('ix_Config_DIM_Municipio_provincia_id'), 'DIM_Municipio', ['provincia_id'], unique=False, schema='Config')

    # ── 4) Config.DIM_CentroMedico ───────────────────────────────────────
    op.create_table(
        'DIM_CentroMedico',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('pais_id', sa.Integer(), nullable=False),
        sa.Column('nombre', sa.String(length=200), nullable=False),
        sa.Column('provincia_id', sa.Integer(), nullable=True),
        sa.Column('municipio_id', sa.Integer(), nullable=True),
        sa.Column('activo', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(['pais_id'], ['Config.DIM_Pais.id'], ),
        sa.ForeignKeyConstraint(['provincia_id'], ['Config.DIM_Provincia.id'], ),
        sa.ForeignKeyConstraint(['municipio_id'], ['Config.DIM_Municipio.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('pais_id', 'nombre', name='UQ_CentroMedico_Pais_Nombre'),
        schema='Config',
    )
    op.create_index(op.f('ix_Config_DIM_CentroMedico_pais_id'), 'DIM_CentroMedico', ['pais_id'], unique=False, schema='Config')

    # ── 5) Config.DIM_CategoriaMedica ────────────────────────────────────
    op.create_table(
        'DIM_CategoriaMedica',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('codigo', sa.String(length=10), nullable=False),
        sa.Column('nombre', sa.String(length=100), nullable=False),
        sa.Column('descripcion', sa.Text(), nullable=True),
        sa.Column('score_min', sa.Numeric(precision=6, scale=4), nullable=False),
        sa.Column('score_max', sa.Numeric(precision=6, scale=4), nullable=False),
        sa.Column('color_dashboard', sa.String(length=30), nullable=True),
        sa.Column('orden', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('activo', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('codigo', name='UQ_CategoriaMedica_Codigo'),
        schema='Config',
    )

    # ── 6) Config.DIM_CriterioCategoria ──────────────────────────────────
    op.create_table(
        'DIM_CriterioCategoria',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('codigo', sa.String(length=50), nullable=False),
        sa.Column('nombre', sa.String(length=150), nullable=False),
        sa.Column('tipo_valor', sa.String(length=20), nullable=False, server_default='NUMERICO'),
        sa.Column('peso', sa.Numeric(precision=5, scale=4), nullable=False, server_default='0'),
        sa.Column('orden', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('activo', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('codigo', name='UQ_CriterioCategoria_Codigo'),
        schema='Config',
    )

    # ── 7) Config.DIM_CriterioCategoriaTabla ─────────────────────────────
    op.create_table(
        'DIM_CriterioCategoriaTabla',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('criterio_id', sa.Integer(), nullable=False),
        sa.Column('pais_id', sa.Integer(), nullable=True),
        sa.Column('rango_desde', sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column('rango_hasta', sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column('etiqueta', sa.String(length=100), nullable=True),
        sa.Column('nivel', sa.Integer(), nullable=False),
        sa.Column('descripcion', sa.String(length=150), nullable=True),
        sa.Column('activo', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(['criterio_id'], ['Config.DIM_CriterioCategoria.id'], ),
        sa.ForeignKeyConstraint(['pais_id'], ['Config.DIM_Pais.id'], ),
        sa.PrimaryKeyConstraint('id'),
        schema='Config',
    )
    op.create_index(op.f('ix_Config_DIM_CriterioCategoriaTabla_criterio_id'), 'DIM_CriterioCategoriaTabla', ['criterio_id'], unique=False, schema='Config')
    op.create_index(op.f('ix_Config_DIM_CriterioCategoriaTabla_pais_id'), 'DIM_CriterioCategoriaTabla', ['pais_id'], unique=False, schema='Config')

    # ── 8) Config.DIM_Medico ─────────────────────────────────────────────
    op.create_table(
        'DIM_Medico',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('pais_id', sa.Integer(), nullable=False),
        sa.Column('codigo', sa.String(length=50), nullable=True),
        sa.Column('nombre', sa.String(length=200), nullable=False),
        sa.Column('especialidad_id', sa.Integer(), nullable=True),
        sa.Column('centro_medico_id', sa.Integer(), nullable=True),
        sa.Column('provincia_id', sa.Integer(), nullable=True),
        sa.Column('municipio_id', sa.Integer(), nullable=True),
        sa.Column('cedula', sa.String(length=30), nullable=True),
        sa.Column('email', sa.String(length=200), nullable=True),
        sa.Column('activo', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(['pais_id'], ['Config.DIM_Pais.id'], ),
        sa.ForeignKeyConstraint(['especialidad_id'], ['Config.DIM_Especialidad.id'], ),
        sa.ForeignKeyConstraint(['centro_medico_id'], ['Config.DIM_CentroMedico.id'], ),
        sa.ForeignKeyConstraint(['provincia_id'], ['Config.DIM_Provincia.id'], ),
        sa.ForeignKeyConstraint(['municipio_id'], ['Config.DIM_Municipio.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('pais_id', 'nombre', name='UQ_Medico_Pais_Nombre'),
        schema='Config',
    )
    op.create_index(op.f('ix_Config_DIM_Medico_pais_id'), 'DIM_Medico', ['pais_id'], unique=False, schema='Config')
    op.create_index(op.f('ix_Config_DIM_Medico_especialidad_id'), 'DIM_Medico', ['especialidad_id'], unique=False, schema='Config')
    op.create_index(op.f('ix_Config_DIM_Medico_centro_medico_id'), 'DIM_Medico', ['centro_medico_id'], unique=False, schema='Config')

    # ── 9) DW.FACT_CategorizacionMedica ──────────────────────────────────
    op.create_table(
        'FACT_CategorizacionMedica',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('pais_id', sa.Integer(), nullable=False),
        sa.Column('linea_id', sa.Integer(), nullable=True),
        sa.Column('gerente_id', sa.Integer(), nullable=True),
        sa.Column('rm_id', sa.Integer(), nullable=False),
        sa.Column('medico_id', sa.Integer(), nullable=False),
        sa.Column('ciclo_id', sa.Integer(), nullable=False),
        sa.Column('pacientes_semana', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('costo_consulta', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('potencial_prescripcion', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('ubicacion_territorial', sa.String(length=50), nullable=True),
        sa.Column('kol', sa.String(length=100), nullable=True),
        sa.Column('nivel_pacientes', sa.Integer(), nullable=True),
        sa.Column('nivel_poder_adquisitivo', sa.Integer(), nullable=True),
        sa.Column('nivel_prescripcion', sa.Integer(), nullable=True),
        sa.Column('nivel_ubicacion', sa.Integer(), nullable=True),
        sa.Column('nivel_kol', sa.Integer(), nullable=True),
        sa.Column('score_pacientes', sa.Numeric(precision=6, scale=4), nullable=False, server_default='0'),
        sa.Column('score_poder_adquisitivo', sa.Numeric(precision=6, scale=4), nullable=False, server_default='0'),
        sa.Column('score_prescripcion', sa.Numeric(precision=6, scale=4), nullable=False, server_default='0'),
        sa.Column('score_ubicacion', sa.Numeric(precision=6, scale=4), nullable=False, server_default='0'),
        sa.Column('score_kol', sa.Numeric(precision=6, scale=4), nullable=False, server_default='0'),
        sa.Column('score_total', sa.Numeric(precision=6, scale=4), nullable=False, server_default='0'),
        sa.Column('categoria_id', sa.Integer(), nullable=True),
        sa.Column('categoria_anterior_id', sa.Integer(), nullable=True),
        sa.Column('observaciones', sa.Text(), nullable=True),
        sa.Column('carga_excel_id', sa.Integer(), nullable=True),
        sa.Column('fecha_calculo', sa.DateTime(), nullable=False),
        sa.Column('usuario_calculo', sa.String(length=100), nullable=True),
        sa.Column('activo', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(['pais_id'], ['Config.DIM_Pais.id'], ),
        sa.ForeignKeyConstraint(['linea_id'], ['Config.DIM_Linea.id'], ),
        sa.ForeignKeyConstraint(['rm_id'], ['Config.DIM_RM.id'], ),
        sa.ForeignKeyConstraint(['medico_id'], ['Config.DIM_Medico.id'], ),
        sa.ForeignKeyConstraint(['ciclo_id'], ['Config.DIM_Ciclo.id'], ),
        sa.ForeignKeyConstraint(['categoria_id'], ['Config.DIM_CategoriaMedica.id'], ),
        sa.ForeignKeyConstraint(['categoria_anterior_id'], ['Config.DIM_CategoriaMedica.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('medico_id', 'ciclo_id', name='UQ_CategorizacionMedica_Medico_Ciclo'),
        schema='DW',
    )
    op.create_index(op.f('ix_DW_FACT_CategorizacionMedica_pais_id'), 'FACT_CategorizacionMedica', ['pais_id'], unique=False, schema='DW')
    op.create_index(op.f('ix_DW_FACT_CategorizacionMedica_rm_id'), 'FACT_CategorizacionMedica', ['rm_id'], unique=False, schema='DW')
    op.create_index(op.f('ix_DW_FACT_CategorizacionMedica_medico_id'), 'FACT_CategorizacionMedica', ['medico_id'], unique=False, schema='DW')
    op.create_index(op.f('ix_DW_FACT_CategorizacionMedica_ciclo_id'), 'FACT_CategorizacionMedica', ['ciclo_id'], unique=False, schema='DW')


def downgrade() -> None:
    op.drop_index(op.f('ix_DW_FACT_CategorizacionMedica_ciclo_id'), table_name='FACT_CategorizacionMedica', schema='DW')
    op.drop_index(op.f('ix_DW_FACT_CategorizacionMedica_medico_id'), table_name='FACT_CategorizacionMedica', schema='DW')
    op.drop_index(op.f('ix_DW_FACT_CategorizacionMedica_rm_id'), table_name='FACT_CategorizacionMedica', schema='DW')
    op.drop_index(op.f('ix_DW_FACT_CategorizacionMedica_pais_id'), table_name='FACT_CategorizacionMedica', schema='DW')
    op.drop_table('FACT_CategorizacionMedica', schema='DW')

    op.drop_index(op.f('ix_Config_DIM_Medico_centro_medico_id'), table_name='DIM_Medico', schema='Config')
    op.drop_index(op.f('ix_Config_DIM_Medico_especialidad_id'), table_name='DIM_Medico', schema='Config')
    op.drop_index(op.f('ix_Config_DIM_Medico_pais_id'), table_name='DIM_Medico', schema='Config')
    op.drop_table('DIM_Medico', schema='Config')

    op.drop_index(op.f('ix_Config_DIM_CriterioCategoriaTabla_pais_id'), table_name='DIM_CriterioCategoriaTabla', schema='Config')
    op.drop_index(op.f('ix_Config_DIM_CriterioCategoriaTabla_criterio_id'), table_name='DIM_CriterioCategoriaTabla', schema='Config')
    op.drop_table('DIM_CriterioCategoriaTabla', schema='Config')

    op.drop_table('DIM_CriterioCategoria', schema='Config')
    op.drop_table('DIM_CategoriaMedica', schema='Config')

    op.drop_index(op.f('ix_Config_DIM_CentroMedico_pais_id'), table_name='DIM_CentroMedico', schema='Config')
    op.drop_table('DIM_CentroMedico', schema='Config')

    op.drop_index(op.f('ix_Config_DIM_Municipio_provincia_id'), table_name='DIM_Municipio', schema='Config')
    op.drop_table('DIM_Municipio', schema='Config')

    op.drop_index(op.f('ix_Config_DIM_Provincia_pais_id'), table_name='DIM_Provincia', schema='Config')
    op.drop_table('DIM_Provincia', schema='Config')

    op.drop_table('DIM_Especialidad', schema='Config')
