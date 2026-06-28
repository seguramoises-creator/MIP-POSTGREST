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

cur.execute("""
SELECT c.id, c.nombre, c.cerrado, c.pais_id, p.nombre AS pais_nombre
FROM [Config].[DIM_Ciclo] c
JOIN [Config].[DIM_Pais] p ON p.id = c.pais_id
WHERE c.nombre LIKE '%C03%'
ORDER BY c.id
""")
print("=== Ciclos C03 ===")
for r in cur.fetchall():
    print(r)

cur.execute("""
SELECT ciclo_id, pais_id, COUNT(*) as filas,
       SUM(CASE WHEN resultado_porcentaje IS NOT NULL THEN 1 ELSE 0 END) as con_pct
FROM [DW].[FACT_ResultadoIndicador]
GROUP BY ciclo_id, pais_id
ORDER BY ciclo_id
""")
print("\n=== KPI cargados por ciclo ===")
for r in cur.fetchall():
    print(r)

conn.close()
