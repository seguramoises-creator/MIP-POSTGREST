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
print("--- DIM_Indicador DO ---")
cur.execute("SELECT COUNT(*) FROM Config.DIM_Indicador WHERE pais_codigo='DO'")
print(cur.fetchone())
print("--- FACT_ResultadoIndicador ciclo_id distintos ---")
cur.execute("SELECT ciclo_id, COUNT(*) n FROM DW.FACT_ResultadoIndicador WHERE pais_codigo='DO' GROUP BY ciclo_id")
for row in cur.fetchall(): print(row)
conn.close()
