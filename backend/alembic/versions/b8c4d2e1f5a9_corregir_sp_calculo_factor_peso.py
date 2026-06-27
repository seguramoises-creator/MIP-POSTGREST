"""Corregir SPs de cálculo: floor-match sin cap + SUM directo para ranking

Revision ID: b8c4d2e1f5a9
Revises: f1a2b3c4d5e6
Create Date: 2026-06-12

CORRECCIONES (pedido explícito del usuario, jun-2026):

El modelo correcto de puntaje es:
  puntos_indicador = factor × peso   (factor viene del BUSCARV en la tabla RM)
  score_total      = SUM(factor_i × peso_i)   para todos los indicadores del RM

  Donde DIM_IndicadorTabla almacena:
    rango_desde = rango_hasta = valor_resultado   (lookup exacto)
    puntos      = ROUND(factor × peso, 4)         (pre-calculado al importar)

BUG 1 — sp_CompletarPuntajesCiclo (corregido):
  ANTES: cumplimiento se acotaba a 100% antes del lookup → EVO_IR (que llega
    a 137%) y VENTAS (>110%) siempre usaban la fila de 100%, ignorando el
    bonus por sobre-cumplimiento.
  AHORA: se elimina el cap; el lookup usa el valor escalado directamente
    (ESCALA=1 → ×100; ESCALA=100 → directo).

BUG 2 — sp_CompletarPuntajesCiclo (corregido):
  ANTES: lookup con BETWEEN rango_desde AND rango_hasta → fallaba porque
    rango_desde = rango_hasta = valor exacto y el valor real tiene decimales
    (p.ej. 88.50 no cae "entre" 88 y 88 con BETWEEN por redondeo).
  AHORA: floor-match:
    SELECT TOP 1 puntos WHERE rango_desde <= valor_lookup ORDER BY rango_desde DESC
    → devuelve la fila cuyo umbral más alto NO supera al valor real.
    Cubre: bajo mínimo (sin fila → 0), rango exacto, sobre-máximo (fila del max).

BUG 3 — sp_GenerarRankingCiclo (corregido):
  ANTES: promedio por módulo + pesos normalizados → IUP en [0,1] × 100
    → score_total no reflejaba el Excel.
  AHORA: score_total = SUM(puntos_obtenidos) directo, donde
    puntos_obtenidos ya es factor × peso del indicador.
    score_total replica exactamente la columna TOTAL del Excel de RMs.
"""
from typing import Sequence, Union

from alembic import op


revision: str = 'b8c4d2e1f5a9'
down_revision: Union[str, Sequence[str], None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


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

    -- ESCALA=1 : resultado_real es fraccion (0-1) → multiplicar ×100 antes del lookup
    -- ESCALA=100: resultado_real ya es el valor directo (%, score, indice)
    -- NO se aplica cap al 100%: EVO_IR puede llegar a 137%, VENTAS a 110%+.
    -- El valor escalado se compara contra DIM_IndicadorTabla.rango_desde (floor-match).
    ;WITH calc AS (
        SELECT
            ri.id,
            ri.pais_id,
            ri.indicador_id,
            ri.resultado_real,
            CASE WHEN ind.escala = 1
                 THEN ri.resultado_real * 100.0
                 ELSE ri.resultado_real
            END AS valor_lookup
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
        ri.puntos_obtenidos =
            -- Lookup tipo BUSCARV-aproximado (floor-match):
            --   Busca la fila con el mayor rango_desde que NO supere al valor.
            --   Si valor < minimo en tabla → ninguna fila devuelta → ISNULL → 0.
            --   Si valor > maximo en tabla → devuelve la fila del maximo (bonus max).
            --   Sin tabla configurada → pass-through acotado a [0,100].
            ISNULL(
                (
                    SELECT TOP 1 t.puntos
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
                    ) THEN
                        -- Sin tabla: devolver el valor escalado acotado a [0,100]
                        CASE WHEN c.valor_lookup < 0   THEN 0
                             WHEN c.valor_lookup > 100 THEN 100
                             ELSE c.valor_lookup END
                    ELSE 0  -- Tabla existe pero valor por debajo del minimo
                END
            ),
        ri.fecha_calculo = @ahora
    FROM DW.FACT_ResultadoIndicador ri
    INNER JOIN calc c ON c.id = ri.id;

    SET @filas_actualizadas = @@ROWCOUNT;

    -- Completar factor_aplicado / puntos_maximos / porcentaje_logro desde DIM_MetaIndicador
    UPDATE ri
    SET
        ri.factor_aplicado  = m.peso,
        ri.puntos_maximos   = m.puntaje_maximo,
        ri.porcentaje_logro =
            CASE
                WHEN m.meta_100 IS NOT NULL AND m.meta_100 <> 0 THEN
                    (ri.resultado_real / m.meta_100) * 100.0
                WHEN m.meta_100 IS NOT NULL AND m.meta_100 = 0 THEN 0
                WHEN m.objetivo  IS NOT NULL AND m.objetivo  <> 0 THEN
                    (ri.resultado_real / m.objetivo) * 100.0
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


SP_GENERAR_RANKING = r"""
CREATE OR ALTER PROCEDURE DW.sp_GenerarRankingCiclo
    @ciclo_id INT,
    @pais_id  INT = NULL,
    @registros_generados INT OUTPUT
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @ahora DATETIME2 = SYSUTCDATETIME();
    SET @registros_generados = 0;

    -- Si no hay datos con puntos calculados -> no tocar nada
    IF NOT EXISTS (
        SELECT 1 FROM DW.FACT_ResultadoIndicador ri
        WHERE ri.ciclo_id = @ciclo_id
          AND ri.activo = 1
          AND ri.puntos_obtenidos IS NOT NULL
          AND (@pais_id IS NULL OR ri.pais_id = @pais_id)
    )
    BEGIN
        RETURN;
    END

    IF OBJECT_ID('tempdb..#resultados') IS NOT NULL DROP TABLE #resultados;

    -- score_total = SUM(puntos_obtenidos) por RM.
    -- Cada puntos_obtenidos = factor × peso (pre-calculado en DIM_IndicadorTabla).
    -- El lookup (sp_CompletarPuntajesCiclo) hace el floor-match y devuelve ese valor.
    -- Por lo tanto score_total replica exactamente la columna TOTAL del Excel:
    --   TOTAL = Σ(factor_i × peso_i)  para los 8 indicadores del RM.
    ;WITH score_rm AS (
        SELECT
            ri.rm_id,
            ri.pais_id,
            SUM(CAST(ri.puntos_obtenidos AS DECIMAL(18,6))) AS score_total
        FROM DW.FACT_ResultadoIndicador ri
        WHERE ri.ciclo_id = @ciclo_id
          AND ri.activo = 1
          AND ri.puntos_obtenidos IS NOT NULL
          AND (@pais_id IS NULL OR ri.pais_id = @pais_id)
        GROUP BY ri.rm_id, ri.pais_id
    ),
    scores AS (
        SELECT
            s.rm_id,
            s.pais_id,
            rm.linea_id,
            rm.gerente_id,
            CAST(s.score_total AS DECIMAL(10,4)) AS score_total
        FROM score_rm s
        INNER JOIN Config.DIM_RM rm ON rm.id = s.rm_id
    ),
    con_categoria AS (
        SELECT
            s.*,
            (
                SELECT TOP 1 cat.id
                FROM Config.DIM_CategoriaDesempeno cat
                WHERE cat.activo = 1
                  AND ISNULL(cat.score_min, -1)      <= s.score_total
                  AND ISNULL(cat.score_max, 999999) >= s.score_total
                ORDER BY cat.id ASC
            ) AS categoria_id
        FROM scores s
    )
    SELECT
        c.*,
        ROW_NUMBER() OVER (ORDER BY c.score_total DESC, c.rm_id ASC) AS posicion_global,
        ROW_NUMBER() OVER (
            PARTITION BY c.linea_id ORDER BY c.score_total DESC, c.rm_id ASC
        ) AS posicion_linea
    INTO #resultados
    FROM con_categoria c;

    -- Capturar posiciones anteriores ANTES de borrar (para mostrar variacion)
    DECLARE @anteriores TABLE (rm_id INT PRIMARY KEY, posicion_anterior INT);
    INSERT INTO @anteriores (rm_id, posicion_anterior)
    SELECT rm_id, posicion_global
    FROM DW.FACT_RankingRM
    WHERE ciclo_id    = @ciclo_id
      AND tipo_ranking = 'MENSUAL'
      AND (@pais_id IS NULL OR pais_id = @pais_id);

    -- DELETE - "borrar e integrar todo de nuevo" (nunca upsert parcial)
    DELETE FROM DW.FACT_ScoreIntegralRM
    WHERE ciclo_id = @ciclo_id
      AND (@pais_id IS NULL OR pais_id = @pais_id);

    DELETE FROM DW.FACT_RankingRM
    WHERE ciclo_id    = @ciclo_id
      AND tipo_ranking = 'MENSUAL'
      AND (@pais_id IS NULL OR pais_id = @pais_id);

    -- INSERT - regenerar desde cero
    INSERT INTO DW.FACT_ScoreIntegralRM
        (pais_id, linea_id, gerente_id, rm_id, ciclo_id,
         score_total, categoria_id, elegible_reconocimiento, fecha_calculo)
    SELECT
        r.pais_id, r.linea_id, r.gerente_id, r.rm_id, @ciclo_id,
        r.score_total, r.categoria_id,
        CASE WHEN r.score_total > 0 THEN 1 ELSE 0 END, @ahora
    FROM #resultados r;

    INSERT INTO DW.FACT_RankingRM
        (pais_id, linea_id, gerente_id, rm_id, ciclo_id, tipo_ranking,
         score_total, categoria_id, posicion_global, posicion_linea,
         posicion_anterior, elegible, fecha_generacion)
    SELECT
        r.pais_id, r.linea_id, r.gerente_id, r.rm_id, @ciclo_id, 'MENSUAL',
        r.score_total, r.categoria_id,
        r.posicion_global, r.posicion_linea, a.posicion_anterior,
        CASE WHEN r.score_total > 0 THEN 1 ELSE 0 END, @ahora
    FROM #resultados r
    LEFT JOIN @anteriores a ON a.rm_id = r.rm_id;

    SET @registros_generados = @@ROWCOUNT;

    DROP TABLE #resultados;
END
"""


def upgrade() -> None:
    # CREATE OR ALTER: actualiza los SPs sin recrear sp_RecalcularCiclo
    # (este orquestador no cambió — sigue llamando a los dos con EXEC)
    op.execute(SP_COMPLETAR_PUNTAJES)
    op.execute(SP_GENERAR_RANKING)


def downgrade() -> None:
    # Restaurar la versión anterior (bug incluido) ejecutando la migración
    # e7a91f4c2b58 de nuevo — se deja como no-op porque el rollback real
    # requeriría re-aplicar el SQL bugueado manualmente.
    pass
