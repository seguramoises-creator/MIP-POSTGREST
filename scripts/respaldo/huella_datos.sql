-- Huella de datos: md5 sobre el conteo EXACTO de filas de cada tabla.
--
-- Sirve para demostrar que dos ambientes (origen y destino de un respaldo)
-- contienen exactamente la misma informacion. Se usa query_to_xml y no
-- pg_stat_user_tables.n_live_tup porque ese ultimo es una ESTIMACION del
-- planificador y cambia con el autovacuum sin que cambie un solo dato.
--
-- Las tablas de auditoria quedan EXCLUIDAS a proposito: crecen con cualquier
-- uso del sistema (hasta un login fallido escribe una fila), asi que sin la
-- exclusion la huella nunca coincide y deja de distinguir una diferencia real
-- de la simple actividad. Nunca borrar filas de auditoria para "cuadrar" un
-- conteo: son append-only por diseno.

SELECT md5(string_agg(t || '=' || c, ',' ORDER BY t)) AS huella,
       count(*)                                        AS tablas,
       sum(c)                                          AS filas
FROM (
    SELECT table_schema || '.' || table_name AS t,
           (xpath('/row/c/text()',
                  query_to_xml('SELECT count(*) AS c FROM '
                               || quote_ident(table_schema) || '.'
                               || quote_ident(table_name),
                               false, true, '')))[1]::text::bigint AS c
    FROM information_schema.tables
    WHERE table_type = 'BASE TABLE'
      AND table_schema NOT IN ('pg_catalog', 'information_schema')
      AND table_name NOT IN ('FACT_Auditoria', 'FACT_AuditoriaSeguridad')
) s;
