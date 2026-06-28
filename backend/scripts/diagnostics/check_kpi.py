# --- credenciales desde backend/.env (parametrizado, no hardcodear) ---
import os as _os, pathlib as _pl
try:
    from dotenv import load_dotenv as _ld
    _ld(_pl.Path(__file__).resolve().parents[2] / '.env')
except Exception:
    pass
os = _os
# ----------------------------------------------------------------------
import pymssql
conn = pymssql.connect('127.0.0.1', 'segura', os.environ.get('DB_PASSWORD', ''), 'SCGCPR', port=1433)
cur = conn.cursor(as_dict=True)

# Ver valores reales en los KPI del ciclo 803
cur.execute("""
SELECT TOP 10
    ri.id,
    ri.rm_id,
    ind.codigo AS indicador_codigo,
    ri.resultado_real,
    ri.resultado_porcentaje,
    ri.puntos_obtenidos
FROM [DW].[FACT_ResultadoIndicador] ri
JOIN [Config].[DIM_Indicador] ind ON ind.id = ri.indicador_id
WHERE ri.ciclo_id = 803 AND ri.pais_id = 71
ORDER BY ri.id
""")
print("=== Muestra de filas ciclo 803 ===")
for r in cur.fetchall():
    print(r)

# Estadísticas de los valores
cur.execute("""
SELECT
    ind.codigo,
    COUNT(*) as filas,
    AVG(CAST(ri.resultado_real AS FLOAT)) as avg_real,
    AVG(CAST(ri.resultado_porcentaje AS FLOAT)) as avg_pct,
    AVG(CAST(ri.puntos_obtenidos AS FLOAT)) as avg_puntos
FROM [DW].[FACT_ResultadoIndicador] ri
JOIN [Config].[DIM_Indicador] ind ON ind.id = ri.indicador_id
WHERE ri.ciclo_id = 803 AND ri.pais_id = 71
GROUP BY ind.codigo
ORDER BY ind.codigo
""")
print("\n=== Promedios por indicador (ciclo 803) ===")
for r in cur.fetchall():
    print(r)

conn.close()
