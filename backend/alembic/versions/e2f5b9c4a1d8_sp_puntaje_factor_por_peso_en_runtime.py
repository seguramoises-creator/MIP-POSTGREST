"""SP: calcular puntos_obtenidos = factor × peso en runtime (no pre-computado)

Revision ID: e2f5b9c4a1d8
Revises: d1f4a8c3e9b2
Create Date: 2026-06-12

CAMBIO DE DISEÑO (solicitado explícitamente):

  ANTES:
    DIM_IndicadorTabla.puntos = factor × peso  (pre-calculado al importar)
    SP: puntos_obtenidos = t.puntos            (lookup directo)

  AHORA:
    DIM_IndicadorTabla.puntos = factor          (solo el factor, ej: 1.08)
    SP: puntos_obtenidos = factor × ponderacion_pct  (calculado en runtime)

  Esto es semánticamente correcto:
    - DIM_IndicadorTabla guarda la TABLA DE FACTORES (lo que se sube con TABLA_RM)
    - DIM_Indicador guarda el PESO del KPI (ponderacion_pct)
    - El resultado 16.2 se calcula DESPUÉS de subir la FACT, en el SP
"""
from typing import Sequence, Union
from alembic import op

revision: str = 'e2f5b9c4a1d8'
down_revision: Union[str, Sequence[str], None] = 'd1f4a8c3e9b2'
branch_labels = None
depends_on = None


SP_COMPLETAR_PUNTAJES = r"""
CREATE OR ALTER PROCEDURE DW.sp_CompletarPuntajesCiclo
    @ciclo_id INT,
    @pais_id  INT = NULL,
    @filas_actualizadas INT OUTPUT
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @ahora DATETIME2 = SYSUTCDATETIME();
    SET @filas_actualizadas = 0;

    -- CTE: escalar resultado_real y traer peso del indicador
    -- ESCALA=1 : fraccion (0-1) → ×100 antes del lookup
    -- ESCALA=100: valor directo (%, score, indice)
    -- Sin cap al 100%: EVO_IR llega a 137%, VENTAS a 110%+
    ;WITH calc AS (
        SELECT
            ri.id,
            ri.pais_id,
            ri.indicador_id,
            ri.resultado_real,
            CASE WHEN ind.escala = 1
                 THEN ri.resultado_real * 100.0
                 ELSE ri.resultado_real
            END AS valor_lookup,
            CAST(ind.ponderacion_pct AS DECIMAL(18,6)) AS peso_indicador
        FROM DW.FACT_ResultadoIndicador ri
        INNER JOIN Config.DIM_Indicador ind ON ind.id = ri.indicador_id
        WHERE ri.ciclo_id = @ciclo_id
          AND ri.activo = 1
          AND ri.resultado_real IS NOT NULL
          AND (@pais_id IS NULL OR ri.pais_id = @pais_id)
    )
    UPDATE ri
    SET
        ri.resultado_porcentaje = c.valor_lookup,
        -- puntos_obtenidos = FACTOR × PESO
        -- FACTOR: lookup floor-match en DIM_IndicadorTabla (puntos = factor puro, ej 1.08)
        -- PESO  : ponderacion_pct de DIM_Indicador (ej 15)
        -- Resultado: 1.08 × 15 = 16.2
        ri.puntos_obtenidos =
            ISNULL(
                (
                    SELECT TOP 1 t.puntos * c.peso_indicador
                    FROM Config.DIM_IndicadorTabla t
                    WHERE t.indicador_id = c.indicador_id
                      AND t.pais_id      = c.pais_id
                      AND t.activo       = 1
                      AND t.rango_desde  <= c.valor_lookup
                    ORDER BY t.rango_desde DESC
                ),
                CASE
                    WHEN NOT EXISTS (
                        SELECT 1 FROM Config.DIM_IndicadorTabla t2
                        WHERE t2.indicador_id = c.indicador_id
                          AND t2.pais_id = c.pais_id
                          AND t2.activo  = 1
                    ) THEN 0   -- Sin tabla configurada → 0
                    ELSE 0     -- Tabla existe pero valor por debajo del mínimo → 0
                END
            ),
        ri.fecha_calculo = @ahora
    FROM DW.FACT_ResultadoIndicador ri
    INNER JOIN calc c ON c.id = ri.id;

    SET @filas_actualizadas = @@ROWCOUNT;

    -- Complementar factor_aplicado / puntos_maximos / porcentaje_logro
    UPDATE ri
    SET
        ri.factor_aplicado  = m.peso,
        ri.puntos_maximos   = m.puntaje_maximo,
        ri.porcentaje_logro =
            CASE
                WHEN m.meta_100 IS NOT NULL AND m.meta_100 <> 0
                    THEN (ri.resultado_real / m.meta_100) * 100.0
                WHEN m.meta_100 IS NOT NULL AND m.meta_100 = 0 THEN 0
                WHEN m.objetivo  IS NOT NULL AND m.objetivo  <> 0
                    THEN (ri.resultado_real / m.objetivo) * 100.0
                WHEN m.objetivo  IS NOT NULL AND m.objetivo  = 0 THEN 0
                ELSE ri.porcentaje_logro
            END
    FROM DW.FACT_ResultadoIndicador ri
    INNER JOIN Config.DIM_MetaIndicador m
           ON m.indicador_id = ri.indicador_id AND m.activo = 1
    WHERE ri.ciclo_id = @ciclo_id
      AND ri.activo = 1
      AND ri.resultado_real IS NOT NULL
      AND (@pais_id IS NULL OR ri.pais_id = @pais_id);
END
"""


def upgrade() -> None:
    op.execute(SP_COMPLETAR_PUNTAJES)


def downgrade() -> None:
    pass  # Rollback manual: re-aplicar migración b8c4d2e1f5a9
