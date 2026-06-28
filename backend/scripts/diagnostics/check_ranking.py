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

# ¿Hay datos en FACT_RankingRM para los ciclos con KPI?
cur.execute("""
SELECT ciclo_id, pais_id, COUNT(*) as rms,
       AVG(CAST(score_total AS FLOAT)) as avg_score
FROM [DW].[FACT_RankingRM]
GROUP BY ciclo_id, pais_id
ORDER BY ciclo_id
""")
print("=== Ranking generado ===")
for r in cur.fetchall():
    print(r)

# Verificar qué devuelve exactamente el endpoint /productividad para ciclo 797
cur.execute("""
SELECT TOP 5
    rm.codigo AS rm_codigo,
    ind.codigo AS indicador_codigo,
    ri.ciclo_id,
    AVG(CAST(ri.resultado_porcentaje AS FLOAT)) AS cumplimiento_pct
FROM [DW].[FACT_ResultadoIndicador] ri
JOIN [Config].[DIM_RM] rm ON rm.id = ri.rm_id
JOIN [Config].[DIM_Indicador] ind ON ind.id = ri.indicador_id
LEFT JOIN [Config].[DIM_Linea] ln ON ln.id = ri.linea_id
LEFT JOIN [Config].[DIM_Gerente] g ON g.id = rm.gerente_id
WHERE ri.activo = 1 AND ri.pais_id = 71 AND ri.ciclo_id = 797
GROUP BY rm.id, rm.codigo, rm.nombre, rm.pais_id, ln.nombre, g.nombre, ind.codigo, ri.ciclo_id
""")
print("\n=== Muestra productividad ciclo 797 ===")
for r in cur.fetchall():
    print(r)

# Qué pais_id tienen los paises en la BD?
cur.execute("SELECT id, codigo, nombre FROM [Config].[DIM_Pais] WHERE activo=1 ORDER BY id")
print("\n=== Países activos ===")
for r in cur.fetchall():
    print(r)

conn.close()
