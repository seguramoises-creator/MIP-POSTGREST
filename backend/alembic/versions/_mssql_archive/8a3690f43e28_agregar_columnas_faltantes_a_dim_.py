"""agregar columnas faltantes a DIM_Indicador y otras DIMs

Revision ID: 8a3690f43e28
Revises: a1c4f9d2b6e0
Create Date: 2026-06-06 04:09:35.091096

Drift detectado por --autogenerate (con include_schemas=True ya activo en
env.py, lo que permitio una comparacion correcta de TODOS los esquemas):

  - Config.DIM_Ciclo.nombre_canonico        (nullable)
  - Config.DIM_Indicador.rol                NOT NULL  -> requiere backfill
  - Config.DIM_Indicador.tipo_periodo       NOT NULL  -> requiere backfill
  - Config.DIM_Indicador.ponderacion_pct    NOT NULL  -> requiere backfill
  - Config.DIM_Indicador.escala             NOT NULL  -> requiere backfill
  - Config.DIM_Indicador.valor_min          (nullable)
  - Config.DIM_Indicador.valor_max          (nullable)
  - Config.DIM_IndicadorTabla.pais_id       NOT NULL + FK -> requiere backfill
  - Config.DIM_Mes.abrev                    (nullable)
  - Config.DIM_Mes.ciclo_mes                (nullable)
  - Config.DIM_RM.cedula                    (nullable)

Las columnas NOT NULL se agregan siguiendo el patron seguro (igual que
pais_id en a1c4f9d2b6e0): NULL -> backfill -> NOT NULL [-> FK], para no
romper las filas existentes (DIM_Indicador tiene 48 filas, DIM_IndicadorTabla
tiene ~1050, segun el preview de importacion).

Los valores de backfill para DIM_Indicador (rol/tipo_periodo/ponderacion_pct/
escala) usan los mismos defaults que define el modelo SQLAlchemy
(`app/models/dimensiones.py`): rol="RM", tipo_periodo="CICLO",
ponderacion_pct=0, escala=1.

IMPORTANTE: revisa DEFAULT_PAIS_ID_INDICADOR_TABLA antes de aplicar en un
entorno con datos reales (debe ser un id valido de Config.DIM_Pais).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8a3690f43e28'
down_revision: Union[str, Sequence[str], None] = 'a1c4f9d2b6e0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Backfill para Config.DIM_IndicadorTabla.pais_id — ajusta al id real de
# Config.DIM_Pais que deben usar las filas existentes (igual criterio que
# se uso para Config.DIM_Indicador.pais_id en a1c4f9d2b6e0).
DEFAULT_PAIS_ID_INDICADOR_TABLA = 1

# Backfill para columnas NOT NULL de Config.DIM_Indicador — mismos defaults
# que declara el modelo (app/models/dimensiones.py).
DEFAULT_ROL = "RM"
DEFAULT_TIPO_PERIODO = "CICLO"
DEFAULT_PONDERACION_PCT = 0
DEFAULT_ESCALA = 1


def upgrade() -> None:
    # --- columnas nullable: se agregan directo, sin riesgo ---
    op.add_column('DIM_Ciclo', sa.Column('nombre_canonico', sa.String(length=50), nullable=True), schema='Config')
    op.add_column('DIM_Indicador', sa.Column('valor_min', sa.Numeric(precision=10, scale=4), nullable=True), schema='Config')
    op.add_column('DIM_Indicador', sa.Column('valor_max', sa.Numeric(precision=10, scale=4), nullable=True), schema='Config')
    op.add_column('DIM_Mes', sa.Column('abrev', sa.String(length=5), nullable=True), schema='Config')
    op.add_column('DIM_Mes', sa.Column('ciclo_mes', sa.Integer(), nullable=True), schema='Config')
    op.add_column('DIM_RM', sa.Column('cedula', sa.String(length=30), nullable=True), schema='Config')

    # --- Config.DIM_Indicador: columnas NOT NULL -> NULL, backfill, NOT NULL ---
    op.add_column('DIM_Indicador', sa.Column('rol', sa.String(length=20), nullable=True), schema='Config')
    op.add_column('DIM_Indicador', sa.Column('tipo_periodo', sa.String(length=10), nullable=True), schema='Config')
    op.add_column('DIM_Indicador', sa.Column('ponderacion_pct', sa.Integer(), nullable=True), schema='Config')
    op.add_column('DIM_Indicador', sa.Column('escala', sa.Integer(), nullable=True), schema='Config')

    op.execute(f"UPDATE [Config].[DIM_Indicador] SET rol = '{DEFAULT_ROL}' WHERE rol IS NULL")
    op.execute(f"UPDATE [Config].[DIM_Indicador] SET tipo_periodo = '{DEFAULT_TIPO_PERIODO}' WHERE tipo_periodo IS NULL")
    op.execute(f"UPDATE [Config].[DIM_Indicador] SET ponderacion_pct = {DEFAULT_PONDERACION_PCT} WHERE ponderacion_pct IS NULL")
    op.execute(f"UPDATE [Config].[DIM_Indicador] SET escala = {DEFAULT_ESCALA} WHERE escala IS NULL")

    op.alter_column('DIM_Indicador', 'rol', existing_type=sa.String(length=20), nullable=False, schema='Config')
    op.alter_column('DIM_Indicador', 'tipo_periodo', existing_type=sa.String(length=10), nullable=False, schema='Config')
    op.alter_column('DIM_Indicador', 'ponderacion_pct', existing_type=sa.Integer(), nullable=False, schema='Config')
    op.alter_column('DIM_Indicador', 'escala', existing_type=sa.Integer(), nullable=False, schema='Config')

    # --- Config.DIM_IndicadorTabla.pais_id: NULL -> backfill -> NOT NULL -> FK ---
    op.add_column('DIM_IndicadorTabla', sa.Column('pais_id', sa.Integer(), nullable=True), schema='Config')
    op.execute(
        f"UPDATE [Config].[DIM_IndicadorTabla] SET pais_id = {DEFAULT_PAIS_ID_INDICADOR_TABLA} "
        f"WHERE pais_id IS NULL"
    )
    op.alter_column(
        'DIM_IndicadorTabla', 'pais_id',
        existing_type=sa.Integer(),
        nullable=False,
        schema='Config',
    )
    op.create_foreign_key(
        'FK_IndicadorTabla_Pais',
        'DIM_IndicadorTabla', 'DIM_Pais',
        ['pais_id'], ['id'],
        source_schema='Config', referent_schema='Config',
    )


def downgrade() -> None:
    op.drop_constraint('FK_IndicadorTabla_Pais', 'DIM_IndicadorTabla', schema='Config', type_='foreignkey')
    op.drop_column('DIM_IndicadorTabla', 'pais_id', schema='Config')

    op.drop_column('DIM_Indicador', 'escala', schema='Config')
    op.drop_column('DIM_Indicador', 'ponderacion_pct', schema='Config')
    op.drop_column('DIM_Indicador', 'tipo_periodo', schema='Config')
    op.drop_column('DIM_Indicador', 'rol', schema='Config')

    op.drop_column('DIM_RM', 'cedula', schema='Config')
    op.drop_column('DIM_Mes', 'ciclo_mes', schema='Config')
    op.drop_column('DIM_Mes', 'abrev', schema='Config')
    op.drop_column('DIM_Indicador', 'valor_max', schema='Config')
    op.drop_column('DIM_Indicador', 'valor_min', schema='Config')
    op.drop_column('DIM_Ciclo', 'nombre_canonico', schema='Config')
