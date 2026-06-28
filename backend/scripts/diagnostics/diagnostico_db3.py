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
conn = pymssql.connect(server='127.0.0.1', port=1433, database='SCGCPR', user='segura', password=os.environ.get('DB_PASSWORD', ''))
cur = conn.cursor()

print("--- FACT_RankingRM muestra (DO) ---")
cur.execute("SELECT TOP 5 rm_id, ciclo_id, pais_codigo, tipo_ranking, posicion_global, score_total FROM DW.FACT_RankingRM WHERE pais_codigo='DO'")
for row in cur.fetchall(): print(row)

print("--- tipo_ranking distintos ---")
cur.execute("SELECT DISTINCT tipo_ranking, COUNT(*) n FROM DW.FACT_RankingRM GROUP BY tipo_ranking")
for row in cur.fetchall(): print(row)

print("--- Ultimo ciclo DO con ranking ---")
cur.execute("""
SELECT TOP 1 r.ciclo_id, c.nombre, c.anio, c.numero
FROM DW.FACT_RankingRM r
JOIN Config.DIM_Ciclo c ON c.id = r.ciclo_id
WHERE r.pais_codigo='DO'
ORDER BY c.anio DESC, c.numero DESC
""")
for row in cur.fetchall(): print(row)

conn.close()
