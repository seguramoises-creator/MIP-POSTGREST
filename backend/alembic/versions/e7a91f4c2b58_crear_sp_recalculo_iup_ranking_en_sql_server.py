"""crear procedimientos almacenados para recalculo de IUP y ranking en SQL Server

Revision ID: e7a91f4c2b58
Revises: d4e8f2b56a91
Create Date: 2026-06-07 12:30:00.000000

Mueve el motor de cálculo de IUP/puntajes/ranking — antes implementado en
Python (app/services/recalculo_service.py + puntaje_service.py) — a
procedimientos almacenados T-SQL que se ejecutan DENTRO de SQL Server.

Motivación (pedido explícito del usuario, jun-2026): que el cálculo NO
dependa de archivos Excel ni de su estructura/nombres de hoja, y que se
ejecute como un proceso de base de datos parametrizado por país + ciclo
(los mismos parámetros que el usuario selecciona en la pantalla "Calcular
IUP y Ranking" del frontend).

Procedimientos creados (esquema DW, junto a las FACT_* que operan):

  - DW.sp_CompletarPuntajesCiclo (@ciclo_id, @pais_id, @filas_actualizadas OUTPUT)
        Replica _completar_puntajes(): para cada fila de
        DW.FACT_ResultadoIndicador del ciclo (activo=1):
          * resultado_porcentaje = resultado_real * 100 si escala=1, si no directo
          * cumplimiento acotado a 100 antes del lookup
          * puntos_obtenidos = lookup en Config.DIM_IndicadorTabla
            (rango_desde<=valor<=rango_hasta; sobre el máximo → puntos del
            rango más alto; sin tabla configurada → valor directo acotado [0,100])
          * factor_aplicado / puntos_maximos / porcentaje_logro desde
            Config.DIM_MetaIndicador (meta_100 u objetivo, lo que esté disponible)

  - DW.sp_GenerarRankingCiclo (@ciclo_id, @pais_id, @registros_generados OUTPUT)
        Replica _generar_ranking(): patrón "borrar e integrar todo de nuevo"
        (delete-then-regenerate, NUNCA upsert parcial) sobre
        DW.FACT_ScoreIntegralRM y DW.FACT_RankingRM (tipo_ranking='MENSUAL'):
          * pesos por módulo desde Config.DIM_Indicador.ponderacion_pct
            (normalizados a que sumen 1; si no hay configuración, usa los
            pesos por defecto GESTION 40% / RESULTADOS 30% / COACHING 15% /
            CAPACITACION 15%, igual que el motor Python)
          * IUP por RM = Σ(promedio_puntos_módulo × peso_módulo), normalizado
            a [0,1] y expresado como score_total en escala 0-100
          * categoría de desempeño por rango de score (Config.DIM_CategoriaDesempeno)
          * posición global y posición por línea (ROW_NUMBER por score desc)
          * posición anterior capturada ANTES del borrado, para mostrar variación
          * si no hay datos con puntos calculados → no escribe nada (igual
            que el warning "sin datos para ranking" del motor Python)

  - DW.sp_RecalcularCiclo (@ciclo_id, @pais_id)
        Orquestador — replica recalcular_ciclo(): aplica el guard de negocio
        "solo ciclo abierto" (Config.DIM_Ciclo.cerrado=0; si está cerrado,
        aborta sin escribir nada y retorna abortado=1+motivo, igual que
        CicloCerradoError en Python), y si procede invoca los dos SP
        anteriores en orden. Devuelve un result set con
        (ciclo_id, abortado, motivo, filas_kpi_actualizadas, rankings_generados)
        — mismo contrato que recalcular_ciclo() — para que
        recalculo_service.py solo necesite ejecutar
        "EXEC DW.sp_RecalcularCiclo @ciclo_id=:c, @pais_id=:p" y leer la fila.

downgrade(): elimina los 3 procedimientos (DROP PROCEDURE IF EXISTS).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e7a91f4c2b58'
down_revision: Union[str, Sequence[str], None] = 'd4e8f2b56a91'
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

    ;WITH calc AS (
        SELECT
            ri.id,
            ri.pais_id,
            ri.indicador_id,
            ri.resultado_real,
            CASE WHEN ind.escala = 1 THEN ri.resultado_real * 100.0 ELSE ri.resultado_real END AS valor_pct
        FROM DW.FACT_ResultadoIndicador ri
        INNER JOIN Config.DIM_Indicador ind ON ind.id = ri.indicador_id
        WHERE ri.ciclo_id = @ciclo_id
          AND ri.activo = 1
          AND ri.resultado_real IS NOT NULL
          AND (@pais_id IS NULL OR ri.pais_id = @pais_id)
    ),
    cumpl AS (
        SELECT
            c.*,
            CASE WHEN c.valor_pct > 100.0 THEN 100.0 ELSE c.valor_pct END AS cumplimiento_pct
        FROM calc c
    ),
    rangos AS (
        SELECT
            c.id,
            (
                SELECT TOP 1 t.puntos
                FROM Config.DIM_IndicadorTabla t
                WHERE t.indicador_id = c.indicador_id AND t.pais_id = c.pais_id AND t.activo = 1
                  AND c.cumplimiento_pct BETWEEN t.rango_desde AND t.rango_hasta
                ORDER BY t.rango_desde ASC
            ) AS puntos_rango,
            (
                SELECT COUNT(*) FROM Config.DIM_IndicadorTabla t
                WHERE t.indicador_id = c.indicador_id AND t.pais_id = c.pais_id AND t.activo = 1
            ) AS num_rangos,
            (
                -- Replica tablas[-1] de Python: ultimo elemento ordenado por
                -- rango_desde ASC = fila con mayor rango_desde (no rango_hasta).
                SELECT TOP 1 t.puntos FROM Config.DIM_IndicadorTabla t
                WHERE t.indicador_id = c.indicador_id AND t.pais_id = c.pais_id AND t.activo = 1
                ORDER BY t.rango_desde DESC
            ) AS puntos_tope,
            (
                SELECT TOP 1 t.rango_hasta FROM Config.DIM_IndicadorTabla t
                WHERE t.indicador_id = c.indicador_id AND t.pais_id = c.pais_id AND t.activo = 1
                ORDER BY t.rango_desde DESC
            ) AS rango_hasta_max
        FROM cumpl c
    )
    UPDATE ri
    SET
        ri.resultado_porcentaje = c.valor_pct,
        ri.puntos_obtenidos =
            CASE
                WHEN r.num_rangos = 0 THEN
                    CASE WHEN c.cumplimiento_pct < 0 THEN 0
                         WHEN c.cumplimiento_pct > 100 THEN 100
                         ELSE c.cumplimiento_pct END
                WHEN r.puntos_rango IS NOT NULL THEN r.puntos_rango
                WHEN c.cumplimiento_pct > r.rango_hasta_max THEN r.puntos_tope
                ELSE 0
            END,
        ri.fecha_calculo = @ahora
    FROM DW.FACT_ResultadoIndicador ri
    INNER JOIN cumpl  c ON c.id = ri.id
    INNER JOIN rangos r ON r.id = ri.id;

    SET @filas_actualizadas = @@ROWCOUNT;

    -- Completar factor_aplicado / puntos_maximos / porcentaje_logro desde DIM_MetaIndicador
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
    INNER JOIN Config.DIM_MetaIndicador m ON m.indicador_id = ri.indicador_id AND m.activo = 1
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

    -- 1) Pesos por modulo: SUM(ponderacion_pct) normalizado a que sumen 1.
    --    Si no hay indicadores con ponderacion configurada, usar defaults
    --    (mismos valores que _get_pesos_modulo en Python).
    DECLARE @pesos TABLE (modulo VARCHAR(50) PRIMARY KEY, peso DECIMAL(18,10));

    IF EXISTS (
        SELECT 1 FROM Config.DIM_Indicador
        WHERE activo = 1 AND ponderacion_pct > 0
          AND (@pais_id IS NULL OR pais_id = @pais_id)
    )
    BEGIN
        ;WITH suma AS (
            SELECT modulo, SUM(CAST(ponderacion_pct AS DECIMAL(18,4))) AS total_pct
            FROM Config.DIM_Indicador
            WHERE activo = 1 AND ponderacion_pct > 0
              AND (@pais_id IS NULL OR pais_id = @pais_id)
            GROUP BY modulo
        )
        INSERT INTO @pesos (modulo, peso)
        SELECT s.modulo, s.total_pct / NULLIF((SELECT SUM(total_pct) FROM suma), 0)
        FROM suma s;
    END
    ELSE
    BEGIN
        INSERT INTO @pesos (modulo, peso) VALUES
            ('GESTION', 0.40), ('RESULTADOS', 0.30), ('COACHING', 0.15), ('CAPACITACION', 0.15);
    END

    -- Garantizar que existan las 4 claves de modulo (peso 0 si faltan)
    INSERT INTO @pesos (modulo, peso)
    SELECT x.m, 0
    FROM (VALUES ('GESTION'), ('RESULTADOS'), ('COACHING'), ('CAPACITACION')) AS x(m)
    WHERE NOT EXISTS (SELECT 1 FROM @pesos p WHERE p.modulo = x.m);

    -- 2) Si no hay datos con puntos calculados -> no tocar nada (igual que
    --    el warning "sin datos para ranking" del motor Python: se conservan
    --    los datos existentes intactos, sin borrar ni regenerar).
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

    -- Agrupar SOLO por rm_id + pais_id para garantizar 1 fila por RM.
    -- linea_id y gerente_id se toman de DIM_RM (asignacion vigente del RM),
    -- no de FACT_ResultadoIndicador (donde pueden variar por fila si el ETL
    -- cargo datos con lineas distintas para el mismo RM).
    ;WITH prom_modulo AS (
        SELECT
            ri.rm_id, ri.pais_id,
            ind.modulo,
            AVG(CAST(ri.puntos_obtenidos AS DECIMAL(18,6))) AS puntaje_prom
        FROM DW.FACT_ResultadoIndicador ri
        INNER JOIN Config.DIM_Indicador ind ON ind.id = ri.indicador_id
        WHERE ri.ciclo_id = @ciclo_id AND ri.activo = 1
          AND ri.puntos_obtenidos IS NOT NULL
          AND (@pais_id IS NULL OR ri.pais_id = @pais_id)
        GROUP BY ri.rm_id, ri.pais_id, ind.modulo
    ),
    iup_bruto AS (
        SELECT
            pm.rm_id, pm.pais_id,
            SUM(pm.puntaje_prom * p.peso) AS iup_bruto
        FROM prom_modulo pm
        INNER JOIN @pesos p ON p.modulo = pm.modulo
        GROUP BY pm.rm_id, pm.pais_id
    ),
    -- Replica exacta de _calcular_iup_rm: si iup_bruto > 1, normalizar /100;
    -- luego acotar a maximo 1; score_total = ese valor final * 100.
    iup_calc AS (
        SELECT
            rm_id, pais_id,
            CASE
                WHEN (CASE WHEN iup_bruto > 1 THEN iup_bruto / 100.0 ELSE iup_bruto END) > 1 THEN 1.0
                ELSE (CASE WHEN iup_bruto > 1 THEN iup_bruto / 100.0 ELSE iup_bruto END)
            END AS iup_final
        FROM iup_bruto
    ),
    scores AS (
        SELECT
            ic.rm_id, ic.pais_id,
            rm.linea_id, rm.gerente_id,
            CAST(ic.iup_final * 100.0 AS DECIMAL(10,4)) AS score_total
        FROM iup_calc ic
        INNER JOIN Config.DIM_RM rm ON rm.id = ic.rm_id
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
        ROW_NUMBER() OVER (PARTITION BY c.linea_id ORDER BY c.score_total DESC, c.rm_id ASC) AS posicion_linea
    INTO #resultados
    FROM con_categoria c;

    -- 3) Capturar posiciones anteriores ANTES de borrar (para mostrar variacion)
    DECLARE @anteriores TABLE (rm_id INT PRIMARY KEY, posicion_anterior INT);
    INSERT INTO @anteriores (rm_id, posicion_anterior)
    SELECT rm_id, posicion_global
    FROM DW.FACT_RankingRM
    WHERE ciclo_id = @ciclo_id
      AND tipo_ranking = 'MENSUAL'
      AND (@pais_id IS NULL OR pais_id = @pais_id);

    -- 4) DELETE - "borrar e integrar todo de nuevo" (regla de negocio: solo
    --    ciclo abierto, nunca upsert parcial - ver docstring del motor Python)
    DELETE FROM DW.FACT_ScoreIntegralRM
    WHERE ciclo_id = @ciclo_id
      AND (@pais_id IS NULL OR pais_id = @pais_id);

    DELETE FROM DW.FACT_RankingRM
    WHERE ciclo_id = @ciclo_id
      AND tipo_ranking = 'MENSUAL'
      AND (@pais_id IS NULL OR pais_id = @pais_id);

    -- 5) INSERT - regenerar desde cero
    INSERT INTO DW.FACT_ScoreIntegralRM
        (pais_id, linea_id, gerente_id, rm_id, ciclo_id, score_total, categoria_id,
         elegible_reconocimiento, fecha_calculo)
    SELECT
        r.pais_id, r.linea_id, r.gerente_id, r.rm_id, @ciclo_id, r.score_total, r.categoria_id,
        CASE WHEN r.score_total > 0 THEN 1 ELSE 0 END, @ahora
    FROM #resultados r;

    INSERT INTO DW.FACT_RankingRM
        (pais_id, linea_id, gerente_id, rm_id, ciclo_id, tipo_ranking, score_total, categoria_id,
         posicion_global, posicion_linea, posicion_anterior, elegible, fecha_generacion)
    SELECT
        r.pais_id, r.linea_id, r.gerente_id, r.rm_id, @ciclo_id, 'MENSUAL', r.score_total, r.categoria_id,
        r.posicion_global, r.posicion_linea, a.posicion_anterior,
        CASE WHEN r.score_total > 0 THEN 1 ELSE 0 END, @ahora
    FROM #resultados r
    LEFT JOIN @anteriores a ON a.rm_id = r.rm_id;

    SET @registros_generados = @@ROWCOUNT;

    DROP TABLE #resultados;
END
"""


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

    -- Guard de negocio "solo ciclo abierto" (replica CicloCerradoError /
    -- validar_ciclo_abierto): si esta cerrado, abortar SIN escribir nada.
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
    # Orden importa: sp_RecalcularCiclo invoca a los otros dos via EXEC,
    # asi que estos deben existir primero.
    op.execute(SP_COMPLETAR_PUNTAJES)
    op.execute(SP_GENERAR_RANKING)
    op.execute(SP_RECALCULAR_CICLO)


def downgrade() -> None:
    op.execute("DROP PROCEDURE IF EXISTS DW.sp_RecalcularCiclo;")
    op.execute("DROP PROCEDURE IF EXISTS DW.sp_GenerarRankingCiclo;")
    op.execute("DROP PROCEDURE IF EXISTS DW.sp_CompletarPuntajesCiclo;")
