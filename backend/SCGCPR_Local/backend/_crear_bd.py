import pymssql, os, sys
from dotenv import load_dotenv
load_dotenv('.env')

server   = os.getenv('DB_SERVER', 'HVHVRD06\SQLEXPRESS')
user     = os.getenv('DB_USER', 'segura')
password = os.getenv('DB_PASSWORD', '')  # tomar de .env; no hardcodear secretos
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
