# ═══════════════════════════════════════════════════════════════════
# SCGCPR — Crear base de datos y esquemas en SQL Server
# ═══════════════════════════════════════════════════════════════════
Write-Host "`n[BD] Creando base de datos SCGCPR y esquemas..." -ForegroundColor Cyan

Set-Location backend
& "venv\Scripts\Activate.ps1"

python -c "
import pymssql, os
from dotenv import load_dotenv
load_dotenv('.env')

server   = os.getenv('DB_SERVER', r'HVHVRD06\SQLEXPRESS')
user     = os.getenv('DB_USER', 'Segura')
password = os.getenv('DB_PASSWORD', '')

print(f'Conectando a {server}...')
try:
    # Conectar a master para crear la BD
    conn = pymssql.connect(server=server, user=user, password=password, database='master')
    conn.autocommit(True)
    cur = conn.cursor()

    # Crear BD si no existe
    cur.execute(\"\"\"
        IF NOT EXISTS (SELECT name FROM sys.databases WHERE name = 'SCGCPR')
        BEGIN
            CREATE DATABASE SCGCPR;
            PRINT 'Base de datos SCGCPR creada';
        END
        ELSE
            PRINT 'Base de datos SCGCPR ya existe';
    \"\"\")
    conn.close()

    # Conectar a SCGCPR para crear esquemas
    conn = pymssql.connect(server=server, user=user, password=password, database='SCGCPR')
    conn.autocommit(True)
    cur = conn.cursor()

    for schema in ['Config', 'DW', 'ETL', 'Audit', 'Security']:
        cur.execute(f\"\"\"
            IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = '{schema}')
                EXEC('CREATE SCHEMA [{schema}]');
        \"\"\")
        print(f'  Esquema [{schema}] OK')

    conn.close()
    print('BD y esquemas listos.')
except Exception as e:
    print(f'Error: {e}')
    raise
"

if ($LASTEXITCODE -eq 0) {
    Write-Host "`n[BD] Creando tablas desde modelos SQLAlchemy..." -ForegroundColor Cyan
    python -c "
from app.db.database import init_db
init_db()
print('Tablas creadas.')
"
    Write-Host "`nBase de datos lista. Ejecutar 3_INICIAR.ps1`n" -ForegroundColor Green
} else {
    Write-Host "`nError al crear la BD. Verificar .env`n" -ForegroundColor Red
}
