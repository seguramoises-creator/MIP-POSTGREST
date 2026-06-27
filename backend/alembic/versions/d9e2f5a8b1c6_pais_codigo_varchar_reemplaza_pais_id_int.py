"""pais_codigo VARCHAR(10) reemplaza pais_id INT en todas las tablas

Revision ID: d9e2f5a8b1c6
Revises: c4d8a1f6b3e7
Create Date: 2026-06-23
"""
from typing import Sequence, Union
from alembic import op

revision: str = 'd9e2f5a8b1c6'
down_revision: Union[str, Sequence[str], None] = 'c4d8a1f6b3e7'
branch_labels = None
depends_on = None

SP_COMPLETAR = r"""
CREATE OR ALTER PROCEDURE DW.sp_CompletarPuntajesCiclo
    @ciclo_id INT, @pais_codigo VARCHAR(10) = NULL, @filas_actualizadas INT OUTPUT
AS BEGIN
    SET NOCOUNT ON;
    DECLARE @ahora DATETIME2 = SYSUTCDATETIME();
    SET @filas_actualizadas = 0;
    ;WITH calc AS (
        SELECT ri.id, ri.resultado_real,
            CASE WHEN ind.escala=1 THEN ri.resultado_real*100.0 ELSE ri.resultado_real END AS valor_pct,
            CAST(ind.ponderacion_pct AS DECIMAL(18,6)) AS ponderacion
        FROM DW.FACT_ResultadoIndicador ri
        INNER JOIN Config.DIM_Indicador ind ON ind.id = ri.indicador_id
        WHERE ri.ciclo_id=@ciclo_id AND ri.activo=1 AND ri.resultado_real IS NOT NULL
          AND (@pais_codigo IS NULL OR ri.pais_codigo=@pais_codigo)
    ), cumpl AS (
        SELECT c.id, c.ponderacion,
            CASE WHEN c.valor_pct<0 THEN 0.0 WHEN c.valor_pct>100.0 THEN 100.0 ELSE c.valor_pct END AS cumplimiento_pct
        FROM calc c
    )
    UPDATE ri SET ri.resultado_porcentaje=c.cumplimiento_pct,
        ri.puntos_obtenidos=(c.cumplimiento_pct/100.0)*c.ponderacion, ri.fecha_calculo=@ahora
    FROM DW.FACT_ResultadoIndicador ri INNER JOIN cumpl c ON c.id=ri.id;
    SET @filas_actualizadas=@@ROWCOUNT;
    UPDATE ri SET ri.factor_aplicado=m.peso, ri.puntos_maximos=m.puntaje_maximo,
        ri.porcentaje_logro=CASE
            WHEN m.meta_100 IS NOT NULL AND m.meta_100<>0 THEN
                CASE WHEN (ri.resultado_real/m.meta_100)*100.0>100.0 THEN 100.0 ELSE (ri.resultado_real/m.meta_100)*100.0 END
            WHEN m.meta_100 IS NOT NULL AND m.meta_100=0 THEN 0
            WHEN m.objetivo IS NOT NULL AND m.objetivo<>0 THEN
                CASE WHEN (ri.resultado_real/m.objetivo)*100.0>100.0 THEN 100.0 ELSE (ri.resultado_real/m.objetivo)*100.0 END
            WHEN m.objetivo IS NOT NULL AND m.objetivo=0 THEN 0 ELSE ri.porcentaje_logro END
    FROM DW.FACT_ResultadoIndicador ri
    INNER JOIN Config.DIM_MetaIndicador m ON m.indicador_id=ri.indicador_id AND m.activo=1
    WHERE ri.ciclo_id=@ciclo_id AND ri.activo=1 AND ri.resultado_real IS NOT NULL
      AND (@pais_codigo IS NULL OR ri.pais_codigo=@pais_codigo);
END
"""

SP_RANKING = r"""
CREATE OR ALTER PROCEDURE DW.sp_GenerarRankingCiclo
    @ciclo_id INT, @pais_codigo VARCHAR(10) = NULL, @registros_generados INT OUTPUT
AS BEGIN
    SET NOCOUNT ON;
    DECLARE @ahora DATETIME2 = SYSUTCDATETIME();
    SET @registros_generados=0;
    IF NOT EXISTS (SELECT 1 FROM DW.FACT_ResultadoIndicador ri
        WHERE ri.ciclo_id=@ciclo_id AND ri.activo=1 AND ri.puntos_obtenidos IS NOT NULL
          AND (@pais_codigo IS NULL OR ri.pais_codigo=@pais_codigo)) BEGIN RETURN; END
    IF OBJECT_ID('tempdb..#resultados') IS NOT NULL DROP TABLE #resultados;
    ;WITH iup AS (
        SELECT ri.rm_id, ri.pais_codigo,
            SUM(CAST(ri.puntos_obtenidos AS DECIMAL(18,6)))*100.0
                /NULLIF(SUM(CAST(ind.ponderacion_pct AS DECIMAL(18,6))),0) AS score_total
        FROM DW.FACT_ResultadoIndicador ri
        INNER JOIN Config.DIM_Indicador ind ON ind.id=ri.indicador_id
        WHERE ri.ciclo_id=@ciclo_id AND ri.activo=1 AND ri.puntos_obtenidos IS NOT NULL
          AND (@pais_codigo IS NULL OR ri.pais_codigo=@pais_codigo)
        GROUP BY ri.rm_id, ri.pais_codigo
    ), scores AS (
        SELECT i.rm_id, i.pais_codigo, rm.linea_id, rm.gerente_id,
            CAST(CASE WHEN i.score_total>100.0 THEN 100.0 WHEN i.score_total<0.0 THEN 0.0 ELSE i.score_total END AS DECIMAL(10,4)) AS score_total
        FROM iup i INNER JOIN Config.DIM_RM rm ON rm.id=i.rm_id
    ), con_cat AS (
        SELECT s.*, (SELECT TOP 1 cat.id FROM Config.DIM_CategoriaDesempeno cat
            WHERE cat.activo=1 AND ISNULL(cat.score_min,-1)<=s.score_total
              AND ISNULL(cat.score_max,999999)>=s.score_total ORDER BY cat.id ASC) AS categoria_id
        FROM scores s
    )
    SELECT c.*, ROW_NUMBER() OVER(ORDER BY c.score_total DESC,c.rm_id ASC) AS posicion_global,
        ROW_NUMBER() OVER(PARTITION BY c.linea_id ORDER BY c.score_total DESC,c.rm_id ASC) AS posicion_linea
    INTO #resultados FROM con_cat c;
    DECLARE @ant TABLE(rm_id INT PRIMARY KEY, posicion_anterior INT);
    INSERT INTO @ant SELECT rm_id,posicion_global FROM DW.FACT_RankingRM
        WHERE ciclo_id=@ciclo_id AND tipo_ranking='MENSUAL'
          AND (@pais_codigo IS NULL OR pais_codigo=@pais_codigo);
    DELETE FROM DW.FACT_ScoreIntegralRM WHERE ciclo_id=@ciclo_id
      AND (@pais_codigo IS NULL OR pais_codigo=@pais_codigo);
    DELETE FROM DW.FACT_RankingRM WHERE ciclo_id=@ciclo_id AND tipo_ranking='MENSUAL'
      AND (@pais_codigo IS NULL OR pais_codigo=@pais_codigo);
    INSERT INTO DW.FACT_ScoreIntegralRM(pais_codigo,linea_id,gerente_id,rm_id,ciclo_id,score_total,categoria_id,elegible_reconocimiento,fecha_calculo)
    SELECT r.pais_codigo,r.linea_id,r.gerente_id,r.rm_id,@ciclo_id,r.score_total,r.categoria_id,
        CASE WHEN r.score_total>=90.0 THEN 1 ELSE 0 END,@ahora FROM #resultados r;
    INSERT INTO DW.FACT_RankingRM(pais_codigo,linea_id,gerente_id,rm_id,ciclo_id,tipo_ranking,score_total,categoria_id,posicion_global,posicion_linea,posicion_anterior,elegible,fecha_generacion)
    SELECT r.pais_codigo,r.linea_id,r.gerente_id,r.rm_id,@ciclo_id,'MENSUAL',r.score_total,r.categoria_id,
        r.posicion_global,r.posicion_linea,a.posicion_anterior,
        CASE WHEN r.score_total>=90.0 THEN 1 ELSE 0 END,@ahora
    FROM #resultados r LEFT JOIN @ant a ON a.rm_id=r.rm_id;
    SET @registros_generados=@@ROWCOUNT;
    DROP TABLE #resultados;
END
"""

SP_RECALCULAR = r"""
CREATE OR ALTER PROCEDURE DW.sp_RecalcularCiclo
    @ciclo_id INT, @pais_codigo VARCHAR(10) = NULL
AS BEGIN
    SET NOCOUNT ON;
    DECLARE @cerrado BIT, @nombre VARCHAR(50);
    SELECT @cerrado=cerrado, @nombre=nombre FROM Config.DIM_Ciclo WHERE id=@ciclo_id;
    IF @cerrado IS NULL BEGIN
        DECLARE @msg NVARCHAR(300)=CONCAT(N'Ciclo ID=',@ciclo_id,N' no encontrado');
        THROW 51001,@msg,1; RETURN;
    END
    IF @cerrado=1 BEGIN
        DECLARE @mot NVARCHAR(500)=CONCAT(N'Ciclo ''',@nombre,N''' (id=',@ciclo_id,N') esta CERRADO');
        SELECT @ciclo_id AS ciclo_id,CAST(1 AS BIT) AS abortado,@mot AS motivo,
               0 AS filas_kpi_actualizadas,0 AS rankings_generados; RETURN;
    END
    DECLARE @kpi INT=0, @rank INT=0;
    EXEC DW.sp_CompletarPuntajesCiclo @ciclo_id=@ciclo_id,@pais_codigo=@pais_codigo,@filas_actualizadas=@kpi OUTPUT;
    EXEC DW.sp_GenerarRankingCiclo @ciclo_id=@ciclo_id,@pais_codigo=@pais_codigo,@registros_generados=@rank OUTPUT;
    SELECT @ciclo_id AS ciclo_id,CAST(0 AS BIT) AS abortado,CAST(NULL AS NVARCHAR(500)) AS motivo,
           @kpi AS filas_kpi_actualizadas,@rank AS rankings_generados;
END
"""


def upgrade() -> None:
    op.execute(SP_COMPLETAR)
    op.execute(SP_RANKING)
    op.execute(SP_RECALCULAR)


def downgrade() -> None:
    pass
