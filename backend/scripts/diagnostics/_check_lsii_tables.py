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

conn = pymssql.connect(
    server="127.0.0.1",
    port=1433,
    user="segura",
    password=os.environ.get('DB_PASSWORD', ''),
    database="SCGCPR",
)
cur = conn.cursor()

cur.execute(
    "SELECT s.name, t.name FROM sys.tables t JOIN sys.schemas s ON t.schema_id = s.schema_id "
    "WHERE (s.name = 'DW' AND t.name LIKE 'FACT_EvaluacionReceptividad%') "
    "OR (s.name = 'Config' AND t.name = 'DIM_ReceptividadOpcion') "
    "ORDER BY s.name, t.name"
)
print("Tablas encontradas:")
for fila in cur.fetchall():
    print(" -", fila[0] + "." + fila[1])

cur.execute("SELECT COUNT(*) FROM [Config].[DIM_ReceptividadOpcion]")
print("Filas en DIM_ReceptividadOpcion:", cur.fetchone()[0])

cur.close()
conn.close()
