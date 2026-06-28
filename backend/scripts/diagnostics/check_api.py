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

# Simular exactamente lo que hace el endpoint /productividad?pais_id=71&ciclo_id=803
cur.execute("""
SELECT TOP 5
    rm.id AS rm_id,
    rm.codigo AS rm_codigo,
    ind.codigo AS indicador_codigo,
    ri.ciclo_id,
    AVG(CAST(ri.resultado_porcentaje AS FLOAT)) AS cumplimiento_pct
FROM [DW].[FACT_ResultadoIndicador] ri
JOIN [Config].[DIM_RM] rm ON rm.id = ri.rm_id
JOIN [Config].[DIM_Indicador] ind ON ind.id = ri.indicador_id
WHERE ri.activo = 1
  AND ri.pais_id = 71
  AND ri.ciclo_id = 803
GROUP BY rm.id, rm.codigo, ind.codigo, ri.ciclo_id
ORDER BY rm.id, ind.codigo
""")
print("=== Muestra datos productividad ciclo 803, pais 71 ===")
rows = cur.fetchall()
for r in rows:
    print(r)
print(f"(mostrando 5 de muchas filas)")

# Count total
cur.execute("""
SELECT COUNT(*) as total
FROM (
    SELECT rm.id, ind.codigo
    FROM [DW].[FACT_ResultadoIndicador] ri
    JOIN [Config].[DIM_RM] rm ON rm.id = ri.rm_id
    JOIN [Config].[DIM_Indicador] ind ON ind.id = ri.indicador_id
    WHERE ri.activo = 1 AND ri.pais_id = 71 AND ri.ciclo_id = 803
    GROUP BY rm.id, ind.codigo
) t
""")
print(f"\nTotal filas agrupadas: {cur.fetchone()['total']}")

conn.close()
