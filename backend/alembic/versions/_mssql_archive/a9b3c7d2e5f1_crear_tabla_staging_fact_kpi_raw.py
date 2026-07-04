"""crear tabla staging ETL.FACT_KPI_RAW

Revision ID: a9b3c7d2e5f1
Revises: f1a2b3c4d5e6
Create Date: 2026-06-11

Tabla de staging que almacena el archivo Excel FACT_KPI_RM tal como viene del
source system, sin ninguna transformación. Permite:
  - Validar los datos originales antes del cálculo
  - Auditar qué llegó en cada carga
  - Reprocesar transformaciones sin re-subir el archivo
"""
from alembic import op
import sqlalchemy as sa

revision = 'a9b3c7d2e5f1'
down_revision = ('f1a2b3c4d5e6', '2c771e676bd7')  # merge de dos ramas
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'FACT_KPI_RAW',
        sa.Column('id',              sa.BigInteger(),    primary_key=True, autoincrement=True),
        sa.Column('carga_id',        sa.Integer(),       sa.ForeignKey('ETL.FACT_CargaExcel.id'), nullable=False),
        # Columnas tal como vienen del Excel fuente
        sa.Column('fact_id',         sa.Integer(),       nullable=True),
        sa.Column('pais_id',         sa.Integer(),       nullable=True),
        sa.Column('pais_codigo',     sa.String(10),      nullable=True),
        sa.Column('rm_id',           sa.Integer(),       nullable=True),
        sa.Column('nombre_rm',       sa.String(200),     nullable=True),
        sa.Column('rm_codigo',       sa.String(50),      nullable=True),
        sa.Column('gerente_id',      sa.Integer(),       nullable=True),
        sa.Column('gerente_codigo',  sa.String(50),      nullable=True),
        sa.Column('linea_id',        sa.Integer(),       nullable=True),
        sa.Column('linea_codigo',    sa.String(50),      nullable=True),
        sa.Column('indicador_id',    sa.Integer(),       nullable=True),
        sa.Column('indicador_codigo',sa.String(50),      nullable=True),
        sa.Column('tipo_periodo',    sa.String(20),      nullable=True),
        sa.Column('ciclo_id',        sa.Integer(),       nullable=True),
        sa.Column('ciclo_nombre',    sa.String(50),      nullable=True),
        sa.Column('mes_id',          sa.Integer(),       nullable=True),
        sa.Column('ciclo_mes',       sa.Integer(),       nullable=True),
        sa.Column('anio',            sa.Integer(),       nullable=True),
        sa.Column('valor_real',      sa.Numeric(18, 6),  nullable=True),
        sa.Column('fecha_carga',     sa.DateTime(),      nullable=False),
        schema='ETL',
    )
    # Índices para las consultas más frecuentes
    op.create_index('ix_FACT_KPI_RAW_carga_id',        'FACT_KPI_RAW', ['carga_id'],        schema='ETL')
    op.create_index('ix_FACT_KPI_RAW_ciclo_id',        'FACT_KPI_RAW', ['ciclo_id'],        schema='ETL')
    op.create_index('ix_FACT_KPI_RAW_rm_codigo',       'FACT_KPI_RAW', ['rm_codigo'],       schema='ETL')
    op.create_index('ix_FACT_KPI_RAW_indicador_codigo','FACT_KPI_RAW', ['indicador_codigo'], schema='ETL')


def downgrade():
    op.drop_index('ix_FACT_KPI_RAW_indicador_codigo', table_name='FACT_KPI_RAW', schema='ETL')
    op.drop_index('ix_FACT_KPI_RAW_rm_codigo',        table_name='FACT_KPI_RAW', schema='ETL')
    op.drop_index('ix_FACT_KPI_RAW_ciclo_id',         table_name='FACT_KPI_RAW', schema='ETL')
    op.drop_index('ix_FACT_KPI_RAW_carga_id',         table_name='FACT_KPI_RAW', schema='ETL')
    op.drop_table('FACT_KPI_RAW', schema='ETL')
