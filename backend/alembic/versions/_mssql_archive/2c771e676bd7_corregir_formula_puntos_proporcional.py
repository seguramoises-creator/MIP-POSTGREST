"""Corregir fórmula de puntos: proporcional en lugar de lookup table

Revision ID: 2c771e676bd7
Revises: e7a91f4c2b58
Create Date: 2026-06-09 10:00:00.000000

CAMBIO DE NEGOCIO (confirmado por el usuario, jun-2026):
  La fórmula anterior calculaba puntos_obtenidos mediante una tabla de rangos
  (DIM_IndicadorTabla). El usuario confirma que el cálculo correcto es
  PROPORCIONAL al cumplimiento:

      puntos_obtenidos = (cumplimiento_pct / 100) × ponderacion_pct

  Ejemplo:
    - Indicador con ponderacion_pct = 10
    - RM alcanza 100% → 10 puntos
    - RM alcanza 90%  →  9 puntos
    - RM alcanza 80%  →  8 puntos

  El IUP (score_total) se calcula como la media ponderada del cumplimiento:

      score_total = SUM(puntos_obtenidos) × 100 / SUM(ponderacion_pct)

  Esto equivale al promedio ponderado de cumplimientos (0-100 scale).

Procedimientos actualizados (CREATE OR ALTER — reemplaza los creados en e7a91f4c2b58):
  - DW.sp_CompletarPuntajesCiclo  → nueva fórmula proporcional
  - DW.sp_GenerarRankingCiclo     → nuevo cálculo de score_total directo
  - DW.sp_RecalcularCiclo         → sin cambio de lógica (orquestador)
"""
from typing import Sequence, Union
from alembic import op


revision: str = '2c771e676bd7'
down_revision: Union[str, Sequence[str], None] = 'e7a91f4c2b58'
branch_labels = None
depends_on = None


# ─────────────────────────────────────────────────────────────────────────────
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

    -- Fórmula: puntos_obtenidos = (cumplimiento_pct / 100) * ponderacion_pct
    -- donde cumplimiento_pct se acota a [0, 100].
    ;WITH calc AS (
        SELECT
            ri.id,
            ri.resultado_real,
            -- Normalizar según escala del indicador
            CASE WHEN ind.escala = 1
                 THEN ri.resultado_real * 100.0
                 ELSE ri.resultado_real
            END AS valor_pct,
            CAST(ind.ponderacion_pct AS DECIMAL(18,6)) AS ponderacion
        FROM DW.FACT_ResultadoIndicador ri
        INNER JOIN Config.DIM_Indicador ind ON ind.id = ri.indicador_id
        WHERE ri.ciclo_id = @ciclo_id
          AND ri.activo = 1
          AND ri.resultado_real IS NOT NULL
          AND (@pais_id IS NULL OR ri.pais_id = @pais_id)
    ),
    cumpl AS (
        SELECT
            c.id,
            c.resultado_real,
            c.ponderacion,
            CASE WHEN c.valor_pct < 0   THEN 0.0
                 WHEN c.valor_pct > 100.0 THEN 100.0
                 ELSE c.valor_pct
            END AS cumplimiento_pct
        FROM calc c
    )
    UPDATE ri
    SET
        ri.resultado_porcentaje = c.cumplimiento_pct,
        ri.puntos_obtenidos     = (c.cumplimiento_pct / 100.0) * c.ponderacion,
        ri.fecha_calculo        = @ahora
    FROM DW.FACT_ResultadoIndicador ri
    INNER JOIN cumpl c ON c.id = ri.id;

    SET @filas_actualizadas = @@ROWCOUNT;

    -- Completar porcentaje_logro desde DIM_MetaIndicador (sin cambios)
    UPDATE ri
    SET
        ri.factor_aplicado  = m.peso,
        ri.puntos_maximos   = m.puntaje_maximo,
        ri.porcentaje_logro =
            CASE
                WHEN m.meta_100 IS NOT NULL AND m.meta_100 <> 0 THEN
                    CASE WHEN (ri.resultado_real / m.meta_100) * 100.0 > 100.0 THEN 100.0
                         ELSE (ri.resultado_real / m.meta_100) * 100.0 END
                WHEN m.meta_100 IS NOT NULL AND m.meta_100 = 0 THEN 0
                WHEN m.objetivo IS NOT NULL AND m.objetivo <> 0 THEN
                    CASE WHEN (ri.resultado_real / m.objetivo) * 100.0 > 100.0 THEN 100.0
                         ELSE (ri.resultado_real / m.objetivo) * 100.0 END
                WHEN m.objetivo IS NOT NULL AND m.objetivo = 0 THEN 0
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

    -- Verificar que hay datos calculados
    IF NOT EXISTS (
        SELECT 1 FROM DW.FACT_ResultadoIndicador ri
        WHERE ri.ciclo_id = @ciclo_id AND ri.activo = 1
          AND ri.puntos_obtenidos IS NOT NULL
          AND (@pais_id IS NULL OR ri.pais_id = @pais_id)
    )
    BEGIN
        RETURN;
    END

    IF OBJECT_ID('tempdb..#resultados') IS NOT NULL DROP TABLE #resultados;

    -- score_total = media ponderada de cumplimientos (0–100)
    --   = SUM(puntos_obtenidos) * 100 / SUM(ponderacion_pct)
    -- donde puntos_obtenidos = (cumplimiento/100) * ponderacion_pct
    -- El resultado ya está en escala 0-100.
    ;WITH iup AS (
        SELECT
            ri.rm_id,
            ri.pais_id,
            SUM(CAST(ri.puntos_obtenidos  AS DECIMAL(18,6))) * 100.0
                / NULLIF(SUM(CAST(ind.ponderacion_pct AS DECIMAL(18,6))), 0) AS score_total
        FROM DW.FACT_ResultadoIndicador ri
        INNER JOIN Config.DIM_Indicador ind ON ind.id = ri.indicador_id
        WHERE ri.ciclo_id = @ciclo_id AND ri.activo = 1
          AND ri.puntos_obtenidos IS NOT NULL
          AND (@pais_id IS NULL OR ri.pais_id = @pais_id)
        GROUP BY ri.rm_id, ri.pais_id
    ),
    scores AS (
        SELECT
            i.rm_id, i.pais_id,
            rm.linea_id, rm.gerente_id,
            CAST(
                CASE WHEN i.score_total > 100.0 THEN 100.0
                     WHEN i.score_total < 0.0   THEN 0.0
                     ELSE i.score_total
                END
            AS DECIMAL(10,4)) AS score_total
        FROM iup i
        INNER JOIN Config.DIM_RM rm ON rm.id = i.rm_id
    ),
    con_categoria AS (
        SELECT
            s.*,
            (
                SELECT TOP 1 cat.id
                FROM Config.DIM_CategoriaDesempeno cat
                WHERE cat.activo = 1
                  AND ISNULL(cat.score_min, -1)       <= s.score_total
                  AND ISNULL(cat.score_max, 999999)   >= s.score_total
                ORDER BY cat.id ASC
            ) AS categoria_id
        FROM scores s
    )
    SELECT
        c.*,
        ROW_NUMBER() OVER (ORDER BY c.score_total DESC, c.rm_id ASC) AS posicion_global,
        ROW_NUMBER() OVER (PARTITION BY c.linea_id ORDER BY c.score_total DESC, c.rm_id ASC) AS posicion_linea
    INTO #resultados
    FROM con_categoria c;

    -- Capturar posiciones anteriores antes de borrar
    DECLARE @anteriores TABLE (rm_id INT PRIMARY KEY, posicion_anterior INT);
    INSERT INTO @anteriores (rm_id, posicion_anterior)
    SELECT rm_id, posicion_global
    FROM DW.FACT_RankingRM
    WHERE ciclo_id = @ciclo_id
      AND tipo_ranking = 'MENSUAL'
      AND (@pais_id IS NULL OR pais_id = @pais_id);

    -- Borrar y regenerar (delete-then-regenerate, nunca upsert parcial)
    DELETE FROM DW.FACT_ScoreIntegralRM
    WHERE ciclo_id = @ciclo_id
      AND (@pais_id IS NULL OR pais_id = @pais_id);

    DELETE FROM DW.FACT_RankingRM
    WHERE ciclo_id = @ciclo_id
      AND tipo_ranking = 'MENSUAL'
      AND (@pais_id IS NULL OR pais_id = @pais_id);

    INSERT INTO DW.FACT_ScoreIntegralRM
        (pais_id, linea_id, gerente_id, rm_id, ciclo_id, score_total, categoria_id,
         elegible_reconocimiento, fecha_calculo)
    SELECT
        r.pais_id, r.linea_id, r.gerente_id, r.rm_id, @ciclo_id,
        r.score_total, r.categoria_id,
        CASE WHEN r.score_total >= 90.0 THEN 1 ELSE 0 END,
        @ahora
    FROM #resultados r;

    INSERT INTO DW.FACT_RankingRM
        (pais_id, linea_id, gerente_id, rm_id, ciclo_id, tipo_ranking, score_total, categoria_id,
         posicion_global, posicion_linea, posicion_anterior, elegible, fecha_generacion)
    SELECT
        r.pais_id, r.linea_id, r.gerente_id, r.rm_id, @ciclo_id, 'MENSUAL',
        r.score_total, r.categoria_id,
        r.posicion_global, r.posicion_linea, a.posicion_anterior,
        CASE WHEN r.score_total >= 90.0 THEN 1 ELSE 0 END,
        @ahora
    FROM #resultados r
    LEFT JOIN @anteriores a ON a.rm_id = r.rm_id;

    SET @registros_generados = @@ROWCOUNT;

    DROP TABLE #resultados;
END
"""

# sp_RecalcularCiclo no cambia (es el orquestador), pero lo re-creamos
# con CREATE OR ALTER para que quede consistente en la BD.
SP_RECALCULAR_CICLO = r"""
CREATE OR ALTER PROCEDURE DW.sp_RecalcularCiclo
    @ciclo_id INT,
    @pais_id  INT = NULL
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @cerrado BIT, @nombre_ciclo VARCHAR(50);
    SELECT @cerrado = cerrado, @nombre_ciclo = nombre
    FROM Config.DIM_Ciclo
    WHERE id = @ciclo_id;

    IF @cerrado IS NULL
    BEGIN
        DECLARE @msg_no_encontrado NVARCHAR(300) = CONCAT(N'Ciclo ID=', @ciclo_id, N' no encontrado');
        THROW 51001, @msg_no_encontrado, 1;
        RETURN;
    END

    IF @cerrado = 1
    BEGIN
        DECLARE @motivo NVARCHAR(500) = CONCAT(
            N'Ciclo ''', @nombre_ciclo, N''' (id=', @ciclo_id,
            N') esta CERRADO - el recalculo no puede modificar ciclos cerrados ',
            N'(snapshot historico inmutable)'
        );
        SELECT
            @ciclo_id          AS ciclo_id,
            CAST(1 AS BIT)     AS abortado,
            @motivo            AS motivo,
            0                  AS filas_kpi_actualizadas,
            0                  AS rankings_generados;
        RETURN;
    END

    DECLARE @filas_kpi INT = 0, @rankings INT = 0;

    EXEC DW.sp_CompletarPuntajesCiclo
        @ciclo_id = @ciclo_id, @pais_id = @pais_id, @filas_actualizadas = @filas_kpi OUTPUT;

    EXEC DW.sp_GenerarRankingCiclo
        @ciclo_id = @ciclo_id, @pais_id = @pais_id, @registros_generados = @rankings OUTPUT;

    SELECT
        @ciclo_id                    AS ciclo_id,
        CAST(0 AS BIT)               AS abortado,
        CAST(NULL AS NVARCHAR(500))  AS motivo,
        @filas_kpi                   AS filas_kpi_actualizadas,
        @rankings                    AS rankings_generados;
END
"""


def upgrade() -> None:
    op.execute(SP_COMPLETAR_PUNTAJES)
    op.execute(SP_GENERAR_RANKING)
    op.execute(SP_RECALCULAR_CICLO)


def downgrade() -> None:
    # No hay downgrade real de lógica de negocio — solo se pueden revertir
    # los procedimientos si se restaura la migración anterior (e7a91f4c2b58).
    pass
