-- ════════════════════════════════════════════════════════════════
-- DIAGNÓSTICO: ¿por qué score_total sale en 0 para ciclo 17 / país 5?
-- Ejecuta cada bloque por separado y comparte los resultados.
-- ════════════════════════════════════════════════════════════════

-- 1) ¿Qué generó el SP en FACT_RankingRM para el ciclo 17?
SELECT TOP 20
    rm_id, pais_id, linea_id, score_total, categoria_id,
    posicion_global, posicion_linea, elegible
FROM DW.FACT_RankingRM
WHERE ciclo_id = 17 AND tipo_ranking = 'MENSUAL' AND pais_id = 5
ORDER BY posicion_global ASC;

-- 2) Promedio de puntos_obtenidos por RM y módulo (esto es lo que
--    consume prom_modulo dentro del SP) — para ver si hay datos
--    y en qué escala vienen
SELECT TOP 30
    ri.rm_id, ind.modulo,
    AVG(CAST(ri.puntos_obtenidos AS DECIMAL(18,6))) AS puntaje_prom,
    COUNT(*) AS filas
FROM DW.FACT_ResultadoIndicador ri
INNER JOIN Config.DIM_Indicador ind ON ind.id = ri.indicador_id
WHERE ri.ciclo_id = 17 AND ri.activo = 1
  AND ri.puntos_obtenidos IS NOT NULL
  AND ri.pais_id = 5
GROUP BY ri.rm_id, ind.modulo
ORDER BY ri.rm_id;

-- 3) Catálogo de módulos + ponderación configurada para país 5
--    (esto es lo que arma la tabla @pesos — el JOIN se hace por
--    p.modulo = pm.modulo, así que el texto debe calzar EXACTO)
SELECT id, codigo, nombre, modulo, ponderacion_pct, peso_iup, activo
FROM Config.DIM_Indicador
WHERE pais_id = 5
ORDER BY modulo, codigo;
