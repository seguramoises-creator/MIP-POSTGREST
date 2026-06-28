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

print("\n--- FACT_RankingRM: pais_codigo y ciclo_id distintos ---")
cur.execute("SELECT DISTINCT pais_codigo, ciclo_id, COUNT(*) as n FROM DW.FACT_RankingRM GROUP BY pais_codigo, ciclo_id")
for row in cur.fetchall():
    print(row)

print("\n--- DIM_Ciclo: ver pais_codigo tambien ---")
cur.execute("SELECT id, nombre, pais_codigo, cerrado FROM Config.DIM_Ciclo ORDER BY id")
for row in cur.fetchall():
    print(row)

print("\n--- FACT_ResultadoIndicador: pais_codigo distintos ---")
cur.execute("SELECT DISTINCT pais_codigo, COUNT(*) as n FROM DW.FACT_ResultadoIndicador GROUP BY pais_codigo")
for row in cur.fetchall():
    print(row)

conn.close()
