"""crear vista V_Ventas_RM con nombre del RM

Revision ID: f1a2b3c4d5e6
Revises: e7a91f4c2b58
Create Date: 2026-06-10

Agrega la vista [DW].[V_Ventas_RM] que enriquece FACT_Ventas con:
  - rm_codigo, rm_nombre  (desde Config.DIM_RM)
  - ciclo_nombre, ciclo_canonico, ciclo_anio, ciclo_numero (desde Config.DIM_Ciclo)
  - pais_nombre           (desde Config.DIM_Pais)
  - linea_nombre          (desde Config.DIM_Linea)
"""
from typing import Union, Sequence
from alembic import op

revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = 'e7a91f4c2b58'
branch_labels = None
depends_on = None

_CREATE = """
CREATE VIEW [DW].[V_Ventas_RM] AS
SELECT
    v.id,
    v.pais_id,
    p.nombre            AS pais_nombre,
    v.linea_id,
    l.nombre            AS linea_nombre,
    v.rm_id,
    rm.codigo           AS rm_codigo,
    rm.nombre           AS rm_nombre,
    v.ciclo_id,
    c.nombre            AS ciclo_nombre,
    c.nombre_canonico   AS ciclo_canonico,
    c.anio              AS ciclo_anio,
    c.numero            AS ciclo_numero,
    v.ventas_reales,
    v.cuota,
    v.cumplimiento_pct,
    v.crecimiento_pct,
    v.puntaje,
    v.fecha_carga
FROM  [DW].[FACT_Ventas]      v
JOIN  [Config].[DIM_RM]       rm ON rm.id = v.rm_id
JOIN  [Config].[DIM_Ciclo]    c  ON c.id  = v.ciclo_id
JOIN  [Config].[DIM_Pais]     p  ON p.id  = v.pais_id
JOIN  [Config].[DIM_Linea]    l  ON l.id  = v.linea_id
"""

_DROP = "DROP VIEW IF EXISTS [DW].[V_Ventas_RM]"


def upgrade() -> None:
    # Solo crear la vista si FACT_Ventas existe en la BD
    conn = op.get_bind()
    result = conn.execute(
        __import__('sqlalchemy').text(
            "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES "
            "WHERE TABLE_SCHEMA = 'DW' AND TABLE_NAME = 'FACT_Ventas'"
        )
    )
    if result.scalar():
        op.execute(_DROP)
        op.execute(_CREATE)


def downgrade() -> None:
    op.execute(_DROP)
