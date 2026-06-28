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

queries = [
    ("FACT_ResultadoIndicador (KPIs cargados)", "SELECT COUNT(*) FROM DW.FACT_ResultadoIndicador"),
    ("FACT_KPI_RAW (staging)", "SELECT COUNT(*) FROM ETL.FACT_KPI_RAW"),
    ("FACT_ScoreIntegralRM", "SELECT COUNT(*) FROM DW.FACT_ScoreIntegralRM"),
    ("FACT_RankingRM", "SELECT COUNT(*) FROM DW.FACT_RankingRM"),
    ("DIM_Ciclo", "SELECT id, nombre, cerrado FROM Config.DIM_Ciclo"),
    ("SP existe?", "SELECT name FROM sys.procedures WHERE schema_id=SCHEMA_ID('DW')"),
]

for label, sql in queries:
    print(f"\n--- {label} ---")
    cur.execute(sql)
    for row in cur.fetchall():
        print(row)

conn.close()
