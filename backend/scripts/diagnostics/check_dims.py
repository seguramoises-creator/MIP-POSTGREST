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
Diagnóstico rápido: verifica que los catálogos DIM estén cargados.
"""
import pymssql

conn = pymssql.connect('127.0.0.1', 'segura', os.environ.get('DB_PASSWORD', ''), 'SCGCPR', port=1433)
cur = conn.cursor(as_dict=True)

tablas = [
    ("Config.DIM_Pais",       "SELECT COUNT(*) AS n FROM [Config].[DIM_Pais] WHERE activo=1"),
    ("Config.DIM_Linea",      "SELECT COUNT(*) AS n FROM [Config].[DIM_Linea] WHERE activo=1"),
    ("Config.DIM_RM",         "SELECT COUNT(*) AS n FROM [Config].[DIM_RM] WHERE activo=1"),
    ("Config.DIM_Indicador",  "SELECT COUNT(*) AS n, STRING_AGG(codigo, ', ') AS codigos FROM [Config].[DIM_Indicador] WHERE activo=1"),
    ("Config.DIM_Ciclo",      "SELECT COUNT(*) AS n FROM [Config].[DIM_Ciclo] WHERE activo=1"),
    ("Config.DIM_IndicadorTabla", "SELECT COUNT(*) AS n FROM [Config].[DIM_IndicadorTabla] WHERE activo=1"),
    ("DW.FACT_ResultadoIndicador", "SELECT COUNT(*) AS n FROM [DW].[FACT_ResultadoIndicador]"),
]

for nombre, sql in tablas:
    try:
        cur.execute(sql)
        r = cur.fetchone()
        info = f"n={r['n']}"
        if 'codigos' in r and r['codigos']:
            info += f" | codigos: {r['codigos']}"
        print(f"  {nombre}: {info}")
    except Exception as e:
        print(f"  {nombre}: ERROR — {e}")

conn.close()
