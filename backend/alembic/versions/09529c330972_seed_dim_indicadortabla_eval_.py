"""seed DIM_IndicadorTabla EVAL_CONOCIMIENTOS

Revision ID: 09529c330972
Revises: 8f19cf7470f8
Create Date: 2026-06-27 17:38:01.245187

Siembra la parametrización RESULTADO->FACTOR del indicador EVAL_CONOCIMIENTOS
(escala 0-10): nota < 8 -> factor 0; nota >= 8 -> factor = nota/10 en pasos de
0.1, rangos contiguos. La columna `puntos` guarda el factor. Idempotente: solo
inserta si el indicador no tiene filas en DIM_IndicadorTabla.
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


revision: str = '09529c330972'
down_revision: Union[str, Sequence[str], None] = '8f19cf7470f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _rangos():
    filas = [(0.0, 7.999, 0.0)]  # nota < 8 -> factor 0
    v = 8.0
    while v <= 10.0001:
        desde = round(v, 2)
        hasta = round(v + 0.099, 3) if v < 10.0 else 10.0
        factor = round(v / 10.0, 2)  # 8.0->0.80 ... 10.0->1.00
        filas.append((desde, hasta, factor))
        v = round(v + 0.1, 2)
    return filas


def upgrade() -> None:
    conn = op.get_bind()
    indicadores = conn.execute(text(
        "SELECT id, pais_codigo, codigo, nombre FROM Config.DIM_Indicador "
        "WHERE codigo = 'EVAL_CONOCIMIENTOS'"
    )).fetchall()
    for ind in indicadores:
        ya = conn.execute(text(
            "SELECT COUNT(*) FROM Config.DIM_IndicadorTabla WHERE indicador_id = :i"
        ), {"i": ind[0]}).scalar()
        if ya and ya > 0:
            continue
        for desde, hasta, puntos in _rangos():
            conn.execute(text(
                "INSERT INTO Config.DIM_IndicadorTabla "
                "(indicador_id, pais_codigo, codigo_indicador, nombre_indicador, "
                " rango_desde, rango_hasta, puntos, descripcion, activo) "
                "VALUES (:i, :p, :c, :n, :d, :h, :pt, :ds, 1)"
            ), {"i": ind[0], "p": ind[1], "c": ind[2], "n": ind[3],
                "d": desde, "h": hasta, "pt": puntos,
                "ds": f"nota {desde}-{hasta} -> factor {puntos}"})


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(text(
        "DELETE t FROM Config.DIM_IndicadorTabla t "
        "JOIN Config.DIM_Indicador i ON i.id = t.indicador_id "
        "WHERE i.codigo = 'EVAL_CONOCIMIENTOS'"
    ))
