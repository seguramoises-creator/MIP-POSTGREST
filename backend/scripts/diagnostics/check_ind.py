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

# Indicadores para pais_id=71 (República Dominicana)
cur.execute("""
SELECT id, pais_id, codigo, nombre, modulo, ponderacion_pct, escala, activo
FROM [Config].[DIM_Indicador]
WHERE pais_id = 71 AND activo = 1
ORDER BY codigo
""")
print("=== Indicadores pais_id=71 ===")
for r in cur.fetchall():
    print(r)

# Ver qué pais_id tienen los indicadores enlazados a los KPI del ciclo 803
cur.execute("""
SELECT DISTINCT ind.id, ind.codigo, ind.pais_id, ind.ponderacion_pct
FROM [DW].[FACT_ResultadoIndicador] ri
JOIN [Config].[DIM_Indicador] ind ON ind.id = ri.indicador_id
WHERE ri.ciclo_id = 803 AND ri.pais_id = 71
ORDER BY ind.codigo
""")
print("\n=== Indicadores reales en KPI ciclo 803 ===")
for r in cur.fetchall():
    print(r)

conn.close()
