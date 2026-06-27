# ═══════════════════════════════════════════════════════════════════
# SCGCPR — Instalación local (sin Docker)
# Ejecutar desde la carpeta SCGCPR_Local como Administrador
# ═══════════════════════════════════════════════════════════════════
Write-Host ""
Write-Host "=====================================" -ForegroundColor Cyan
Write-Host "  SCGCPR — Instalación Local" -ForegroundColor Cyan
Write-Host "=====================================" -ForegroundColor Cyan

# 1. Verificar Python
Write-Host "`n[1/5] Verificando Python..." -ForegroundColor Yellow
$v = python --version 2>&1
if ($LASTEXITCODE -ne 0) { Write-Host "Python no encontrado. Instalar desde python.org" -ForegroundColor Red; exit 1 }
Write-Host "  OK: $v" -ForegroundColor Green

# 2. Crear entorno virtual
Set-Location backend
Write-Host "`n[2/5] Creando entorno virtual..." -ForegroundColor Yellow
if (-Not (Test-Path "venv")) { python -m venv venv }
Write-Host "  OK: venv creado" -ForegroundColor Green

# 3. Activar e instalar dependencias
Write-Host "`n[3/5] Instalando dependencias Python..." -ForegroundColor Yellow
& "venv\Scripts\Activate.ps1"
pip install -r requirements.txt --quiet
if ($LASTEXITCODE -ne 0) { Write-Host "Error instalando dependencias" -ForegroundColor Red; exit 1 }
Write-Host "  OK: dependencias instaladas" -ForegroundColor Green

# 4. Crear carpetas de trabajo
Write-Host "`n[4/5] Creando carpetas..." -ForegroundColor Yellow
@("uploads","processed","errors","reports","logs") | ForEach-Object {
    if (-Not (Test-Path $_)) { New-Item -ItemType Directory -Path $_ | Out-Null }
}
Write-Host "  OK: carpetas listas" -ForegroundColor Green

# 5. Verificar conexión a SQL Server
Write-Host "`n[5/5] Verificando conexión a SQL Server..." -ForegroundColor Yellow
$test = python -c "
from app.db.database import check_db_connection
import sys
sys.exit(0 if check_db_connection() else 1)
" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "  ERROR: No se puede conectar a SQL Server" -ForegroundColor Red
    Write-Host "  Verificar: servidor, usuario, contraseña en backend\.env" -ForegroundColor Yellow
    exit 1
}
Write-Host "  OK: SQL Server conectado" -ForegroundColor Green

Write-Host "`n=====================================" -ForegroundColor Green
Write-Host "  INSTALACION COMPLETADA" -ForegroundColor Green
Write-Host "=====================================" -ForegroundColor Green
Write-Host "`nEjecutar 2_CREAR_BD.ps1 como siguiente paso`n" -ForegroundColor Cyan
