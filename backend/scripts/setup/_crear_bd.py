# --- credenciales desde backend/.env (parametrizado, no hardcodear) ---
import os as _os, pathlib as _pl
try:
    from dotenv import load_dotenv as _ld
    _ld(_pl.Path(__file__).resolve().parents[2] / '.env')
except Exception:
    pass
os = _os
# ----------------------------------------------------------------------
import pymssql, os, sys
from dotenv import load_dotenv
load_dotenv('.env')

server   = os.getenv('DB_SERVER', r'HVHVRD06\SQLEXPRESS')
user     = os.getenv('DB_USER', 'segura')
password = os.getenv('DB_PASSWORD', os.environ.get('DB_PASSWORD', ''))
db_name  = os.getenv('DB_NAME', 'SCGCPR')

print(f"  Conectando a {server} con usuario {user}...")
try:
    conn = pymssql.connect(server=server, user=user, password=password, database='master')
    conn.autocommit(True)
    cur = conn.cursor()
    cur.execute("IF NOT EXISTS (SELECT name FROM sys.databases WHERE name = N'SCGCPR') CREATE DATABASE [SCGCPR]")
    conn.close()
    print("  Base de datos SCGCPR OK")

    conn = pymssql.connect(server=server, user=user, password=password, database=db_name)
    conn.autocommit(True)
    cur = conn.cursor()
    for schema in ["Config", "DW", "ETL", "Audit", "Security"]:
        cur.execute(f"IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name='{schema}') EXEC('CREATE SCHEMA [{schema}]')")
        print(f"  Esquema [{schema}] OK")
    conn.close()
    sys.exit(0)
except Exception as e:
    print(f"  Error: {e}")
    sys.exit(1)
