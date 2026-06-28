# --- credenciales desde backend/.env (parametrizado, no hardcodear) ---
import os as _os, pathlib as _pl
try:
    from dotenv import load_dotenv as _ld
    _ld(_pl.Path(__file__).resolve().parents[2] / '.env')
except Exception:
    pass
os = _os
# ----------------------------------------------------------------------
"""
Script diagnóstico — muestra errores de los últimos jobs ETL.
Ejecutar: python check_job_errors.py
"""
import pymssql, json

conn = pymssql.connect('127.0.0.1', 'segura', os.environ.get('DB_PASSWORD', ''), 'SCGCPR', port=1433)
cur = conn.cursor(as_dict=True)

cur.execute("""
SELECT TOP 5 id, estado, modo, total_filas, filas_exitosas, filas_error,
       log_errores, log_advertencias, fecha_inicio, fecha_fin
FROM [ETL].[FACT_CargaExcel]
ORDER BY id DESC
""")

for r in cur.fetchall():
    print(f"\n=== Job {r['id']} | modo={r['modo']} | estado={r['estado']}")
    print(f"    total={r['total_filas']} | exitosas={r['filas_exitosas']} | errores={r['filas_error']}")
    print(f"    inicio={r['fecha_inicio']} | fin={r['fecha_fin']}")
    if r['log_errores']:
        errs = json.loads(r['log_errores'])
        print(f"  === PRIMEROS 5 ERRORES ({len(errs)} total) ===")
        for e in errs[:5]:
            print(f"    {e}")
    if r['log_advertencias']:
        advs = json.loads(r['log_advertencias'])
        print(f"  === PRIMERA ADVERTENCIA ===")
        print(f"    {advs[0] if advs else 'ninguna'}")

conn.close()
