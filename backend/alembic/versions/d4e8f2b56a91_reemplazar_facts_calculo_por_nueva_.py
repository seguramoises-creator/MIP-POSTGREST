"""reemplazar FACT_RendimientoComercial/Ranking/Reconocimiento por nueva familia de FACTs calculados

Revision ID: d4e8f2b56a91
Revises: b3d4e6a91c2f
Create Date: 2026-06-07 00:00:00.000000

REDISEÑO del módulo de cálculo (jun-2026), alineado a la estructura real de
FACT_MIP_FINAL.xlsx. Se eliminan 3 tablas y se crean 9 nuevas en su lugar:

ELIMINADAS (DW):
  - FACT_RendimientoComercial  → reemplazada por FACT_ResultadoIndicador
        (misma función: tabla de ENTRADA del ETL; estructura más rica,
        adoptada de la hoja FACT_RESULTADO_INDICADOR del Excel)
  - FACT_Ranking               → reemplazada por FACT_RankingRM + FACT_RankingGerente
        (se separa el ranking de RM del de Gerente, según hojas
        FACT_RANKING_RM / FACT_RANKING_GERENTE; los componentes IUP por
        módulo dejan de almacenarse — se calculan dinámicamente desde
        FACT_ResultadoIndicador agrupado por DIM_Indicador.modulo)
  - FACT_Reconocimiento        → reemplazada por FACT_ReconocimientoRM
        (mismo propósito; conserva certificado_generado/url/aprobado_por
        porque reconocimiento_service ya genera certificados PDF con ellos)

CREADAS — calculadas, alimentadas 100% por el motor de recálculo (DW):
  - FACT_ScoreIntegralRM   (replica FACT_SCORE_INTEGRAL_RM — score consolidado por RM/ciclo)
  - FACT_RankingRM         (replica FACT_RANKING_RM)
  - FACT_RankingGerente    (replica FACT_RANKING_GERENTE — nuevo: ranking de GD)
  - FACT_ReconocimientoRM  (replica FACT_RECONOCIMIENTO_RM)
  - FACT_ScorecardIndicador (replica FACT_SCORECARD_INDICADOR — resumen por indicador/ciclo)
  - FACT_DistribucionEquipo (replica FACT_DISTRIBUCION_EQUIPO — conteo por categoría de desempeño)
  - FACT_DashboardEjecutivo (replica FACT_DASHBOARD_EJECUTIVO — KPIs pre-calculados del dashboard)
  - FACT_TendenciaCiclo     (replica FACT_TENDENCIA_CICLO — serie histórica por ciclo)

CREADA — entrada (DW):
  - FACT_ResultadoIndicador (reemplaza a FACT_RendimientoComercial como input del ETL)

Las tablas FACT_Ventas, FACT_EVOIR, FACT_Coaching, FACT_Capacitacion,
FACT_Auditoria y FACT_CargaExcel NO se modifican (decisión del usuario:
siguen siendo entradas detalladas vigentes que alimentan los indicadores).

⚠️ Esta migración ELIMINA datos existentes en FACT_RendimientoComercial,
FACT_Ranking y FACT_Reconocimiento (DROP TABLE). Es una decisión explícita
del usuario ("se deben eliminar las demás facts que existen en la base de
datos y crear estas nuevas"), no un efecto colateral.

Modelos correspondientes: app/models/hechos.py
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4e8f2b56a91'
down_revision: Union[str, Sequence[str], None] = 'b3d4e6a91c2f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1) Eliminar tablas viejas (solo si existen) ─────────────────────
    # Nota: no se invoca drop_index explícito porque SQL Server elimina los
    # índices junto con la tabla al hacer DROP TABLE. Además, esta BD puede
    # no tener creadas algunas de estas tablas viejas, así que verificamos
    # existencia antes de intentar el DROP (evita error 3701).
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tablas_dw = set(inspector.get_table_names(schema='DW'))

    for nombre_tabla in ('FACT_Reconocimiento', 'FACT_Ranking', 'FACT_RendimientoComercial'):
        if nombre_tabla in tablas_dw:
            op.drop_table(nombre_tabla, schema='DW')

    # ── 2) Crear FACT_ResultadoIndicador (entrada — reemplaza RendimientoComercial) ─
    op.create_table(
        'FACT_ResultadoIndicador',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('pais_id', sa.Integer(), nullable=False),
        sa.Column('linea_id', sa.Integer(), nullable=False),
        sa.Column('gerente_id', sa.Integer(), nullable=True),
        sa.Column('rm_id', sa.Integer(), nullable=False),
        sa.Column('indicador_id', sa.Integer(), nullable=False),
        sa.Column('ciclo_id', sa.Integer(), nullable=False),
        sa.Column('mes_id', sa.Integer(), nullable=True),
        sa.Column('resultado_real', sa.Numeric(precision=14, scale=4), nullable=False, server_default='0'),
        sa.Column('resultado_porcentaje', sa.Numeric(precision=8, scale=4), nullable=True),
        sa.Column('factor_aplicado', sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column('puntos_obtenidos', sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column('puntos_maximos', sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column('porcentaje_logro', sa.Numeric(precision=8, scale=4), nullable=True),
        sa.Column('carga_excel_id', sa.Integer(), nullable=True),
        sa.Column('fecha_carga', sa.DateTime(), nullable=False),
        sa.Column('fecha_calculo', sa.DateTime(), nullable=True),
        sa.Column('activo', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(['ciclo_id'], ['Config.DIM_Ciclo.id'], ),
        sa.ForeignKeyConstraint(['indicador_id'], ['Config.DIM_Indicador.id'], ),
        sa.ForeignKeyConstraint(['linea_id'], ['Config.DIM_Linea.id'], ),
        sa.ForeignKeyConstraint(['pais_id'], ['Config.DIM_Pais.id'], ),
        sa.ForeignKeyConstraint(['rm_id'], ['Config.DIM_RM.id'], ),
        sa.PrimaryKeyConstraint('id'),
        schema='DW',
    )
    op.create_index(op.f('ix_DW_FACT_ResultadoIndicador_pais_id'), 'FACT_ResultadoIndicador', ['pais_id'], unique=False, schema='DW')
    op.create_index(op.f('ix_DW_FACT_ResultadoIndicador_rm_id'), 'FACT_ResultadoIndicador', ['rm_id'], unique=False, schema='DW')
    op.create_index(op.f('ix_DW_FACT_ResultadoIndicador_indicador_id'), 'FACT_ResultadoIndicador', ['indicador_id'], unique=False, schema='DW')
    op.create_index(op.f('ix_DW_FACT_ResultadoIndicador_ciclo_id'), 'FACT_ResultadoIndicador', ['ciclo_id'], unique=False, schema='DW')
    op.create_index(op.f('ix_DW_FACT_ResultadoIndicador_fecha_carga'), 'FACT_ResultadoIndicador', ['fecha_carga'], unique=False, schema='DW')

    # ── 3) Crear FACT_ScoreIntegralRM (calculada) ───────────────────────
    op.create_table(
        'FACT_ScoreIntegralRM',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('pais_id', sa.Integer(), nullable=False),
        sa.Column('linea_id', sa.Integer(), nullable=True),
        sa.Column('gerente_id', sa.Integer(), nullable=True),
        sa.Column('rm_id', sa.Integer(), nullable=False),
        sa.Column('ciclo_id', sa.Integer(), nullable=False),
        sa.Column('score_total', sa.Numeric(precision=10, scale=4), nullable=False, server_default='0'),
        sa.Column('categoria_id', sa.Integer(), nullable=True),
        sa.Column('elegible_reconocimiento', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('fecha_calculo', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['categoria_id'], ['Config.DIM_CategoriaDesempeno.id'], ),
        sa.ForeignKeyConstraint(['ciclo_id'], ['Config.DIM_Ciclo.id'], ),
        sa.ForeignKeyConstraint(['linea_id'], ['Config.DIM_Linea.id'], ),
        sa.ForeignKeyConstraint(['pais_id'], ['Config.DIM_Pais.id'], ),
        sa.ForeignKeyConstraint(['rm_id'], ['Config.DIM_RM.id'], ),
        sa.PrimaryKeyConstraint('id'),
        schema='DW',
    )
    op.create_index(op.f('ix_DW_FACT_ScoreIntegralRM_pais_id'), 'FACT_ScoreIntegralRM', ['pais_id'], unique=False, schema='DW')
    op.create_index(op.f('ix_DW_FACT_ScoreIntegralRM_rm_id'), 'FACT_ScoreIntegralRM', ['rm_id'], unique=False, schema='DW')
    op.create_index(op.f('ix_DW_FACT_ScoreIntegralRM_ciclo_id'), 'FACT_ScoreIntegralRM', ['ciclo_id'], unique=False, schema='DW')

    # ── 4) Crear FACT_RankingRM (calculada — reemplaza FACT_Ranking para RM) ─
    op.create_table(
        'FACT_RankingRM',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('pais_id', sa.Integer(), nullable=False),
        sa.Column('linea_id', sa.Integer(), nullable=True),
        sa.Column('gerente_id', sa.Integer(), nullable=True),
        sa.Column('rm_id', sa.Integer(), nullable=False),
        sa.Column('ciclo_id', sa.Integer(), nullable=True),
        sa.Column('tipo_ranking', sa.String(length=30), nullable=False),
        sa.Column('score_total', sa.Numeric(precision=10, scale=4), nullable=False, server_default='0'),
        sa.Column('categoria_id', sa.Integer(), nullable=True),
        sa.Column('posicion_global', sa.Integer(), nullable=False),
        sa.Column('posicion_linea', sa.Integer(), nullable=True),
        sa.Column('posicion_anterior', sa.Integer(), nullable=True),
        sa.Column('elegible', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('fecha_generacion', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['categoria_id'], ['Config.DIM_CategoriaDesempeno.id'], ),
        sa.ForeignKeyConstraint(['ciclo_id'], ['Config.DIM_Ciclo.id'], ),
        sa.ForeignKeyConstraint(['linea_id'], ['Config.DIM_Linea.id'], ),
        sa.ForeignKeyConstraint(['pais_id'], ['Config.DIM_Pais.id'], ),
        sa.ForeignKeyConstraint(['rm_id'], ['Config.DIM_RM.id'], ),
        sa.PrimaryKeyConstraint('id'),
        schema='DW',
    )
    op.create_index(op.f('ix_DW_FACT_RankingRM_pais_id'), 'FACT_RankingRM', ['pais_id'], unique=False, schema='DW')
    op.create_index(op.f('ix_DW_FACT_RankingRM_rm_id'), 'FACT_RankingRM', ['rm_id'], unique=False, schema='DW')

    # ── 5) Crear FACT_RankingGerente (calculada — NUEVA) ─────────────────
    op.create_table(
        'FACT_RankingGerente',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('pais_id', sa.Integer(), nullable=False),
        sa.Column('gerente_id', sa.Integer(), nullable=False),
        sa.Column('ciclo_id', sa.Integer(), nullable=True),
        sa.Column('score_total', sa.Numeric(precision=10, scale=4), nullable=False, server_default='0'),
        sa.Column('posicion', sa.Integer(), nullable=False),
        sa.Column('metodo_calculo', sa.String(length=50), nullable=True),
        sa.Column('fecha_generacion', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['ciclo_id'], ['Config.DIM_Ciclo.id'], ),
        sa.ForeignKeyConstraint(['gerente_id'], ['Config.DIM_Gerente.id'], ),
        sa.ForeignKeyConstraint(['pais_id'], ['Config.DIM_Pais.id'], ),
        sa.PrimaryKeyConstraint('id'),
        schema='DW',
    )
    op.create_index(op.f('ix_DW_FACT_RankingGerente_pais_id'), 'FACT_RankingGerente', ['pais_id'], unique=False, schema='DW')
    op.create_index(op.f('ix_DW_FACT_RankingGerente_gerente_id'), 'FACT_RankingGerente', ['gerente_id'], unique=False, schema='DW')

    # ── 6) Crear FACT_ReconocimientoRM (calculada — reemplaza FACT_Reconocimiento) ─
    op.create_table(
        'FACT_ReconocimientoRM',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('pais_id', sa.Integer(), nullable=False),
        sa.Column('linea_id', sa.Integer(), nullable=True),
        sa.Column('gerente_id', sa.Integer(), nullable=True),
        sa.Column('rm_id', sa.Integer(), nullable=True),
        sa.Column('premio_id', sa.Integer(), nullable=False),
        sa.Column('ciclo_id', sa.Integer(), nullable=True),
        sa.Column('score_total', sa.Numeric(precision=10, scale=4), nullable=False, server_default='0'),
        sa.Column('posicion_linea', sa.Integer(), nullable=True),
        sa.Column('posicion_ranking', sa.Integer(), nullable=True),
        sa.Column('elegible', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('certificado_generado', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('certificado_url', sa.String(length=500), nullable=True),
        sa.Column('aprobado_por', sa.String(length=200), nullable=True),
        sa.Column('observaciones', sa.Text(), nullable=True),
        sa.Column('fecha_calculo', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['ciclo_id'], ['Config.DIM_Ciclo.id'], ),
        sa.ForeignKeyConstraint(['linea_id'], ['Config.DIM_Linea.id'], ),
        sa.ForeignKeyConstraint(['pais_id'], ['Config.DIM_Pais.id'], ),
        sa.ForeignKeyConstraint(['premio_id'], ['Config.DIM_Premio.id'], ),
        sa.ForeignKeyConstraint(['rm_id'], ['Config.DIM_RM.id'], ),
        sa.PrimaryKeyConstraint('id'),
        schema='DW',
    )
    op.create_index(op.f('ix_DW_FACT_ReconocimientoRM_pais_id'), 'FACT_ReconocimientoRM', ['pais_id'], unique=False, schema='DW')

    # ── 7) Crear FACT_ScorecardIndicador (calculada — NUEVA) ─────────────
    op.create_table(
        'FACT_ScorecardIndicador',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('pais_id', sa.Integer(), nullable=False),
        sa.Column('ciclo_id', sa.Integer(), nullable=False),
        sa.Column('indicador_id', sa.Integer(), nullable=False),
        sa.Column('peso_indicador', sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column('resultado_promedio', sa.Numeric(precision=14, scale=4), nullable=True),
        sa.Column('score_promedio', sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column('categoria_id', sa.Integer(), nullable=True),
        sa.Column('variacion_vs_ciclo_anterior', sa.Numeric(precision=8, scale=4), nullable=True),
        sa.Column('fecha_calculo', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['categoria_id'], ['Config.DIM_CategoriaDesempeno.id'], ),
        sa.ForeignKeyConstraint(['ciclo_id'], ['Config.DIM_Ciclo.id'], ),
        sa.ForeignKeyConstraint(['indicador_id'], ['Config.DIM_Indicador.id'], ),
        sa.ForeignKeyConstraint(['pais_id'], ['Config.DIM_Pais.id'], ),
        sa.PrimaryKeyConstraint('id'),
        schema='DW',
    )
    op.create_index(op.f('ix_DW_FACT_ScorecardIndicador_pais_id'), 'FACT_ScorecardIndicador', ['pais_id'], unique=False, schema='DW')
    op.create_index(op.f('ix_DW_FACT_ScorecardIndicador_ciclo_id'), 'FACT_ScorecardIndicador', ['ciclo_id'], unique=False, schema='DW')
    op.create_index(op.f('ix_DW_FACT_ScorecardIndicador_indicador_id'), 'FACT_ScorecardIndicador', ['indicador_id'], unique=False, schema='DW')

    # ── 8) Crear FACT_DistribucionEquipo (calculada — NUEVA) ─────────────
    op.create_table(
        'FACT_DistribucionEquipo',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('pais_id', sa.Integer(), nullable=False),
        sa.Column('ciclo_id', sa.Integer(), nullable=False),
        sa.Column('categoria_id', sa.Integer(), nullable=False),
        sa.Column('cantidad_rm', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('porcentaje_rm', sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column('fecha_calculo', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['categoria_id'], ['Config.DIM_CategoriaDesempeno.id'], ),
        sa.ForeignKeyConstraint(['ciclo_id'], ['Config.DIM_Ciclo.id'], ),
        sa.ForeignKeyConstraint(['pais_id'], ['Config.DIM_Pais.id'], ),
        sa.PrimaryKeyConstraint('id'),
        schema='DW',
    )
    op.create_index(op.f('ix_DW_FACT_DistribucionEquipo_pais_id'), 'FACT_DistribucionEquipo', ['pais_id'], unique=False, schema='DW')
    op.create_index(op.f('ix_DW_FACT_DistribucionEquipo_ciclo_id'), 'FACT_DistribucionEquipo', ['ciclo_id'], unique=False, schema='DW')

    # ── 9) Crear FACT_DashboardEjecutivo (calculada — NUEVA) ─────────────
    op.create_table(
        'FACT_DashboardEjecutivo',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('pais_id', sa.Integer(), nullable=False),
        sa.Column('ciclo_id', sa.Integer(), nullable=False),
        sa.Column('kpi_dashboard_id', sa.Integer(), nullable=False),
        sa.Column('valor', sa.Numeric(precision=16, scale=4), nullable=True),
        sa.Column('valor_anterior', sa.Numeric(precision=16, scale=4), nullable=True),
        sa.Column('variacion', sa.Numeric(precision=16, scale=4), nullable=True),
        sa.Column('unidad', sa.String(length=30), nullable=True),
        sa.Column('fuente_calculo', sa.String(length=200), nullable=True),
        sa.Column('fecha_calculo', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['ciclo_id'], ['Config.DIM_Ciclo.id'], ),
        sa.ForeignKeyConstraint(['kpi_dashboard_id'], ['Config.DIM_KpiDashboard.id'], ),
        sa.ForeignKeyConstraint(['pais_id'], ['Config.DIM_Pais.id'], ),
        sa.PrimaryKeyConstraint('id'),
        schema='DW',
    )
    op.create_index(op.f('ix_DW_FACT_DashboardEjecutivo_pais_id'), 'FACT_DashboardEjecutivo', ['pais_id'], unique=False, schema='DW')
    op.create_index(op.f('ix_DW_FACT_DashboardEjecutivo_ciclo_id'), 'FACT_DashboardEjecutivo', ['ciclo_id'], unique=False, schema='DW')
    op.create_index(op.f('ix_DW_FACT_DashboardEjecutivo_kpi_dashboard_id'), 'FACT_DashboardEjecutivo', ['kpi_dashboard_id'], unique=False, schema='DW')

    # ── 10) Crear FACT_TendenciaCiclo (calculada — NUEVA) ────────────────
    op.create_table(
        'FACT_TendenciaCiclo',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('pais_id', sa.Integer(), nullable=False),
        sa.Column('ciclo_id', sa.Integer(), nullable=False),
        sa.Column('score_promedio', sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column('score_minimo', sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column('score_maximo', sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column('total_rm', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('fecha_calculo', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['ciclo_id'], ['Config.DIM_Ciclo.id'], ),
        sa.ForeignKeyConstraint(['pais_id'], ['Config.DIM_Pais.id'], ),
        sa.PrimaryKeyConstraint('id'),
        schema='DW',
    )
    op.create_index(op.f('ix_DW_FACT_TendenciaCiclo_pais_id'), 'FACT_TendenciaCiclo', ['pais_id'], unique=False, schema='DW')
    op.create_index(op.f('ix_DW_FACT_TendenciaCiclo_ciclo_id'), 'FACT_TendenciaCiclo', ['ciclo_id'], unique=False, schema='DW')


def downgrade() -> None:
    # ── Eliminar tablas nuevas (orden inverso de creación) ───────────────
    op.drop_index(op.f('ix_DW_FACT_TendenciaCiclo_ciclo_id'), table_name='FACT_TendenciaCiclo', schema='DW')
    op.drop_index(op.f('ix_DW_FACT_TendenciaCiclo_pais_id'), table_name='FACT_TendenciaCiclo', schema='DW')
    op.drop_table('FACT_TendenciaCiclo', schema='DW')

    op.drop_index(op.f('ix_DW_FACT_DashboardEjecutivo_kpi_dashboard_id'), table_name='FACT_DashboardEjecutivo', schema='DW')
    op.drop_index(op.f('ix_DW_FACT_DashboardEjecutivo_ciclo_id'), table_name='FACT_DashboardEjecutivo', schema='DW')
    op.drop_index(op.f('ix_DW_FACT_DashboardEjecutivo_pais_id'), table_name='FACT_DashboardEjecutivo', schema='DW')
    op.drop_table('FACT_DashboardEjecutivo', schema='DW')

    op.drop_index(op.f('ix_DW_FACT_DistribucionEquipo_ciclo_id'), table_name='FACT_DistribucionEquipo', schema='DW')
    op.drop_index(op.f('ix_DW_FACT_DistribucionEquipo_pais_id'), table_name='FACT_DistribucionEquipo', schema='DW')
    op.drop_table('FACT_DistribucionEquipo', schema='DW')

    op.drop_index(op.f('ix_DW_FACT_ScorecardIndicador_indicador_id'), table_name='FACT_ScorecardIndicador', schema='DW')
    op.drop_index(op.f('ix_DW_FACT_ScorecardIndicador_ciclo_id'), table_name='FACT_ScorecardIndicador', schema='DW')
    op.drop_index(op.f('ix_DW_FACT_ScorecardIndicador_pais_id'), table_name='FACT_ScorecardIndicador', schema='DW')
    op.drop_table('FACT_ScorecardIndicador', schema='DW')

    op.drop_index(op.f('ix_DW_FACT_ReconocimientoRM_pais_id'), table_name='FACT_ReconocimientoRM', schema='DW')
    op.drop_table('FACT_ReconocimientoRM', schema='DW')

    op.drop_index(op.f('ix_DW_FACT_RankingGerente_gerente_id'), table_name='FACT_RankingGerente', schema='DW')
    op.drop_index(op.f('ix_DW_FACT_RankingGerente_pais_id'), table_name='FACT_RankingGerente', schema='DW')
    op.drop_table('FACT_RankingGerente', schema='DW')

    op.drop_index(op.f('ix_DW_FACT_RankingRM_rm_id'), table_name='FACT_RankingRM', schema='DW')
    op.drop_index(op.f('ix_DW_FACT_RankingRM_pais_id'), table_name='FACT_RankingRM', schema='DW')
    op.drop_table('FACT_RankingRM', schema='DW')

    op.drop_index(op.f('ix_DW_FACT_ScoreIntegralRM_ciclo_id'), table_name='FACT_ScoreIntegralRM', schema='DW')
    op.drop_index(op.f('ix_DW_FACT_ScoreIntegralRM_rm_id'), table_name='FACT_ScoreIntegralRM', schema='DW')
    op.drop_index(op.f('ix_DW_FACT_ScoreIntegralRM_pais_id'), table_name='FACT_ScoreIntegralRM', schema='DW')
    op.drop_table('FACT_ScoreIntegralRM', schema='DW')

    op.drop_index(op.f('ix_DW_FACT_ResultadoIndicador_fecha_carga'), table_name='FACT_ResultadoIndicador', schema='DW')
    op.drop_index(op.f('ix_DW_FACT_ResultadoIndicador_ciclo_id'), table_name='FACT_ResultadoIndicador', schema='DW')
    op.drop_index(op.f('ix_DW_FACT_ResultadoIndicador_indicador_id'), table_name='FACT_ResultadoIndicador', schema='DW')
    op.drop_index(op.f('ix_DW_FACT_ResultadoIndicador_rm_id'), table_name='FACT_ResultadoIndicador', schema='DW')
    op.drop_index(op.f('ix_DW_FACT_ResultadoIndicador_pais_id'), table_name='FACT_ResultadoIndicador', schema='DW')
    op.drop_table('FACT_ResultadoIndicador', schema='DW')

    # ── Recrear tablas viejas (estructura original — snapshot del baseline) ─
    op.create_table(
        'FACT_RendimientoComercial',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('pais_id', sa.Integer(), nullable=False),
        sa.Column('linea_id', sa.Integer(), nullable=False),
        sa.Column('gerente_id', sa.Integer(), nullable=True),
        sa.Column('rm_id', sa.Integer(), nullable=False),
        sa.Column('indicador_id', sa.Integer(), nullable=False),
        sa.Column('ciclo_id', sa.Integer(), nullable=False),
        sa.Column('mes_id', sa.Integer(), nullable=True),
        sa.Column('valor_real', sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column('valor_meta', sa.Numeric(precision=14, scale=4), nullable=True),
        sa.Column('porcentaje_cumplimiento', sa.Numeric(precision=8, scale=4), nullable=True),
        sa.Column('puntaje', sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column('carga_excel_id', sa.Integer(), nullable=True),
        sa.Column('fecha_carga', sa.DateTime(), nullable=False),
        sa.Column('activo', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(['ciclo_id'], ['Config.DIM_Ciclo.id'], ),
        sa.ForeignKeyConstraint(['indicador_id'], ['Config.DIM_Indicador.id'], ),
        sa.ForeignKeyConstraint(['pais_id'], ['Config.DIM_Pais.id'], ),
        sa.ForeignKeyConstraint(['rm_id'], ['Config.DIM_RM.id'], ),
        sa.PrimaryKeyConstraint('id'),
        schema='DW',
    )
    op.create_index(op.f('ix_DW_FACT_RendimientoComercial_ciclo_id'), 'FACT_RendimientoComercial', ['ciclo_id'], unique=False, schema='DW')
    op.create_index(op.f('ix_DW_FACT_RendimientoComercial_fecha_carga'), 'FACT_RendimientoComercial', ['fecha_carga'], unique=False, schema='DW')
    op.create_index(op.f('ix_DW_FACT_RendimientoComercial_indicador_id'), 'FACT_RendimientoComercial', ['indicador_id'], unique=False, schema='DW')
    op.create_index(op.f('ix_DW_FACT_RendimientoComercial_pais_id'), 'FACT_RendimientoComercial', ['pais_id'], unique=False, schema='DW')
    op.create_index(op.f('ix_DW_FACT_RendimientoComercial_rm_id'), 'FACT_RendimientoComercial', ['rm_id'], unique=False, schema='DW')

    op.create_table(
        'FACT_Ranking',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('pais_id', sa.Integer(), nullable=False),
        sa.Column('linea_id', sa.Integer(), nullable=True),
        sa.Column('rm_id', sa.Integer(), nullable=False),
        sa.Column('ciclo_id', sa.Integer(), nullable=True),
        sa.Column('mes_id', sa.Integer(), nullable=True),
        sa.Column('tipo_ranking', sa.String(length=30), nullable=False),
        sa.Column('iup_total', sa.Numeric(precision=10, scale=4), nullable=False),
        sa.Column('iup_productividad', sa.Numeric(precision=10, scale=4), nullable=False),
        sa.Column('iup_comercial', sa.Numeric(precision=10, scale=4), nullable=False),
        sa.Column('iup_coaching', sa.Numeric(precision=10, scale=4), nullable=False),
        sa.Column('iup_capacitacion', sa.Numeric(precision=10, scale=4), nullable=False),
        sa.Column('iup_consistencia', sa.Numeric(precision=10, scale=4), nullable=False),
        sa.Column('posicion', sa.Integer(), nullable=False),
        sa.Column('posicion_anterior', sa.Integer(), nullable=True),
        sa.Column('elegible', sa.Boolean(), nullable=False),
        sa.Column('fecha_generacion', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['pais_id'], ['Config.DIM_Pais.id'], ),
        sa.ForeignKeyConstraint(['rm_id'], ['Config.DIM_RM.id'], ),
        sa.PrimaryKeyConstraint('id'),
        schema='DW',
    )
    op.create_index(op.f('ix_DW_FACT_Ranking_pais_id'), 'FACT_Ranking', ['pais_id'], unique=False, schema='DW')
    op.create_index(op.f('ix_DW_FACT_Ranking_rm_id'), 'FACT_Ranking', ['rm_id'], unique=False, schema='DW')

    op.create_table(
        'FACT_Reconocimiento',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('pais_id', sa.Integer(), nullable=False),
        sa.Column('rm_id', sa.Integer(), nullable=True),
        sa.Column('gerente_id', sa.Integer(), nullable=True),
        sa.Column('premio_id', sa.Integer(), nullable=False),
        sa.Column('ciclo_id', sa.Integer(), nullable=True),
        sa.Column('iup_al_momento', sa.Numeric(precision=10, scale=4), nullable=False),
        sa.Column('posicion_ranking', sa.Integer(), nullable=True),
        sa.Column('certificado_generado', sa.Boolean(), nullable=False),
        sa.Column('certificado_url', sa.String(length=500), nullable=True),
        sa.Column('aprobado_por', sa.String(length=200), nullable=True),
        sa.Column('fecha_reconocimiento', sa.DateTime(), nullable=False),
        sa.Column('observaciones', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['pais_id'], ['Config.DIM_Pais.id'], ),
        sa.ForeignKeyConstraint(['premio_id'], ['Config.DIM_Premio.id'], ),
        sa.PrimaryKeyConstraint('id'),
        schema='DW',
    )
    op.create_index(op.f('ix_DW_FACT_Reconocimiento_pais_id'), 'FACT_Reconocimiento', ['pais_id'], unique=False, schema='DW')
