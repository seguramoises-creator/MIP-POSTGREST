# SCGCPR - Script de Instalacion y Arranque Completo
# Ejecutar: PowerShell -ExecutionPolicy Bypass -File INSTALAR_Y_EJECUTAR.ps1

function Titulo($texto) {
    Write-Host ""
    Write-Host ("=" * 60) -ForegroundColor Cyan
    Write-Host "  $texto" -ForegroundColor Cyan
    Write-Host ("=" * 60) -ForegroundColor Cyan
    Write-Host ""
}
function OK($texto)  { Write-Host "  [OK] $texto" -ForegroundColor Green }
function INFO($texto){ Write-Host "  [>>] $texto" -ForegroundColor Yellow }
function ERR($texto) { Write-Host "  [!!] $texto" -ForegroundColor Red }

function Pausa($msg) {
    Write-Host ""
    Write-Host ("-" * 60) -ForegroundColor DarkGray
    Write-Host "  $msg" -ForegroundColor White
    Write-Host ("-" * 60) -ForegroundColor DarkGray
    Read-Host "  Presiona ENTER para continuar"
    Write-Host ""
}

# ---------------------------------------------------------------------------
# PASO 1 - INSTALACION
# ---------------------------------------------------------------------------
Titulo "PASO 1 de 3 - Instalacion de dependencias Python"

INFO "Verificando Python..."
$pyVer = python --version 2>&1
if ($LASTEXITCODE -ne 0) {
    ERR "Python no encontrado. Instalar desde python.org"
    Read-Host "Presiona ENTER para salir"; exit 1
}
OK "$pyVer detectado"

Set-Location backend

INFO "Creando entorno virtual..."
if (-Not (Test-Path "venv")) { python -m venv venv }
OK "Entorno virtual listo"

INFO "Activando entorno..."
& "venv\Scripts\Activate.ps1"

INFO "Actualizando pip, setuptools y wheel..."
python -m pip install --upgrade pip setuptools setuptools_scm wheel --quiet 2>&1 | Out-Null
OK "Herramientas base actualizadas"

INFO "Instalando pymssql (driver SQL Server)..."
python -m pip install pymssql --quiet 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    ERR "Error instalando pymssql"
    Read-Host "Presiona ENTER para salir"; exit 1
}
OK "pymssql instalado"

INFO "Instalando resto de dependencias..."
python -m pip install -r requirements.txt --quiet 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    ERR "Error instalando dependencias"
    Read-Host "Presiona ENTER para salir"; exit 1
}
OK "Todas las dependencias instaladas"

INFO "Creando carpetas de trabajo..."
@("uploads","processed","errors","reports","logs") | ForEach-Object {
    if (-Not (Test-Path $_)) { New-Item -ItemType Directory -Path $_ | Out-Null }
}
OK "Carpetas listas: uploads, processed, errors, reports, logs"

INFO "Verificando conexion a SQL Server..."
python _check_conn.py
if ($LASTEXITCODE -ne 0) {
    ERR "No se puede conectar a SQL Server"
    Write-Host ""
    Write-Host "  Valores en .env:" -ForegroundColor Yellow
    Get-Content ".env" | Where-Object { $_ -match "^DB_" } | ForEach-Object {
        Write-Host "    $_" -ForegroundColor Gray
    }
    Write-Host ""
    Read-Host "  Corrige el .env y presiona ENTER para reintentar"
    python _check_conn.py
    if ($LASTEXITCODE -ne 0) { ERR "Sin conexion. Saliendo."; exit 1 }
}
OK "Conexion a SQL Server exitosa"

Pausa "PASO 1 COMPLETADO - Dependencias instaladas y SQL Server conectado"

# ---------------------------------------------------------------------------
# PASO 2 - CREAR BASE DE DATOS Y TABLAS
# ---------------------------------------------------------------------------
Set-Location ..
Titulo "PASO 2 de 3 - Creacion de base de datos SCGCPR"
Set-Location backend
& "venv\Scripts\Activate.ps1"

INFO "Creando base de datos SCGCPR y esquemas..."
python _crear_bd.py
if ($LASTEXITCODE -ne 0) {
    ERR "Error creando la base de datos"
    Read-Host "Presiona ENTER para salir"; exit 1
}
OK "Base de datos y esquemas listos"

INFO "Creando tablas..."
python _crear_tablas.py
OK "Tablas creadas en SQL Server"

Pausa "PASO 2 COMPLETADO - Base de datos lista con todas las tablas"

# ---------------------------------------------------------------------------
# PASO 3 - INICIAR SERVIDOR
# ---------------------------------------------------------------------------
Set-Location ..
Titulo "PASO 3 de 3 - Iniciando servidor SCGCPR"
Set-Location backend
& "venv\Scripts\Activate.ps1"

Write-Host "  Abrir en el navegador:" -ForegroundColor White
Write-Host "    http://localhost:8000/api/v1/docs   <- Swagger UI" -ForegroundColor Cyan
Write-Host "    http://localhost:8000/health        <- Estado" -ForegroundColor Cyan
Write-Host "    Ctrl+C para detener" -ForegroundColor Yellow
Write-Host ""

Pausa "Listo - presiona ENTER para iniciar el servidor"

Write-Host ""
Write-Host ("=" * 60) -ForegroundColor Green
Write-Host "  SCGCPR corriendo en http://localhost:8000" -ForegroundColor Green
Write-Host ("=" * 60) -ForegroundColor Green
Write-Host ""

python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
