-- ¿Qué combinaciones (ciclo, país) tienen ranking con score_total = 0?
-- Esto nos dice si el "0.0" del dashboard viene de OTROS ciclos/países
-- que aún no se han recalculado con el SP corregido.
SELECT
    r.ciclo_id, c.nombre AS ciclo_nombre, r.pais_id, p.nombre AS pais_nombre,
    COUNT(*) AS total_filas,
    SUM(CASE WHEN r.score_total = 0 THEN 1 ELSE 0 END) AS filas_en_cero,
    MAX(r.score_total) AS score_max,
    MAX(r.fecha_generacion) AS ultima_generacion
FROM DW.FACT_RankingRM r
INNER JOIN Config.DIM_Ciclo c ON c.id = r.ciclo_id
INNER JOIN Config.DIM_Pais  p ON p.id = r.pais_id
WHERE r.tipo_ranking = 'MENSUAL'
GROUP BY r.ciclo_id, c.nombre, r.pais_id, p.nombre
ORDER BY filas_en_cero DESC, r.ciclo_id DESC;
