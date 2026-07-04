# ===================================================================
# MSM / SCGCPR - Instalar el backend como Servicio de Windows (NSSM)
# ===================================================================
# Requisitos previos:
#   1. Python 3.13 instalado y entorno virtual creado en backend\venv
#      (cd backend; python -m venv venv; .\venv\Scripts\pip install -r requirements.txt)
#   2. backend\.env configurado para produccion (APP_ENV=production, DEBUG=false,
#      JWT_SECRET_KEY fuerte, CORS_ORIGINS y ALLOWED_HOSTS con https://vista-mip.com)
#   3. NSSM descargado desde https://nssm.cc/download y nssm.exe copiado a
#      C:\Tools\nssm\nssm.exe (o ajustar -NssmPath al ejecutar este script)
#
# Uso (PowerShell como Administrador):
#   .\instalar_servicio_backend.ps1
#   .\instalar_servicio_backend.ps1 -NssmPath "D:\nssm\nssm.exe" -Puerto 8000
#
# Que hace:
#   - Crea el servicio de Windows "MSM-Backend" que ejecuta uvicorn
#     (sin --reload, con --proxy-headers para confiar en IIS/ARR)
#   - Configura inicio automatico y reinicio ante fallos
#   - Redirige stdout/stderr a backend\logs\service_stdout.log / service_stderr.log
# ===================================================================

param(
    [string]$NssmPath   = "C:\Tools\nssm\nssm.exe",
    [string]$ProyectoDir = "C:\Users\Lenovo\Proyecto\MSM",
    [string]$ServiceName = "MSM-Backend",
    [string]$Host_       = "127.0.0.1",
    [int]$Puerto         = 8000,
    [int]$Workers        = 2
)

$ErrorActionPreference = "Stop"
# Evita que la salida por stderr de comandos nativos (nssm.exe) se trate como
# error terminante en PowerShell 7.3+ (PSNativeCommandUseErrorActionPreference).
$PSNativeCommandUseErrorActionPreference = $false

function Test-Administrador {
    $actual = [Security.Principal.WindowsIdentity]::GetCurrent()
    $esAdmin = (New-Object Security.Principal.WindowsPrincipal($actual)).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
    if (-not $esAdmin) {
        Write-Host "ERROR: Este script debe ejecutarse como Administrador." -ForegroundColor Red
        exit 1
    }
}

Write-Host ""
Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host "  MSM - Instalacion del servicio de backend (NSSM)" -ForegroundColor Cyan
Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host ""

Test-Administrador

if (-not (Test-Path $NssmPath)) {
    Write-Host "ERROR: No se encontro nssm.exe en: $NssmPath" -ForegroundColor Red
    Write-Host "Descarguelo de https://nssm.cc/download y ajuste -NssmPath." -ForegroundColor Yellow
    exit 1
}

$BackendDir = Join-Path $ProyectoDir "backend"
$VenvPython = Join-Path $BackendDir "venv\Scripts\python.exe"
$LogsDir    = Join-Path $BackendDir "logs"

if (-not (Test-Path $VenvPython)) {
    Write-Host "ERROR: No se encontro el entorno virtual en: $VenvPython" -ForegroundColor Red
    Write-Host "Ejecute primero: cd backend; python -m venv venv; .\venv\Scripts\pip install -r requirements.txt" -ForegroundColor Yellow
    exit 1
}

New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null

# Argumentos de uvicorn:
#   --proxy-headers + --forwarded-allow-ips=127.0.0.1 -> confia en X-Forwarded-* enviados por IIS/ARR
#   sin --reload (modo produccion)
$UvicornArgs = "-m uvicorn app.main:app --host $Host_ --port $Puerto --workers $Workers " + `
               "--proxy-headers --forwarded-allow-ips=127.0.0.1"

Write-Host "Deteniendo/eliminando servicio previo (si existe)..." -ForegroundColor Yellow
try { & $NssmPath stop $ServiceName *>$null } catch {}
try { & $NssmPath remove $ServiceName confirm *>$null } catch {}

Write-Host "Instalando servicio '$ServiceName'..." -ForegroundColor Cyan
& $NssmPath install $ServiceName $VenvPython $UvicornArgs

& $NssmPath set $ServiceName AppDirectory $BackendDir
& $NssmPath set $ServiceName DisplayName "MSM SCGCPR - Backend FastAPI"
& $NssmPath set $ServiceName Description "Backend FastAPI del sistema MIP (MSM/SCGCPR), servido internamente y expuesto via IIS como proxy inverso en https://vista-mip.com"
& $NssmPath set $ServiceName Start SERVICE_AUTO_START
& $NssmPath set $ServiceName AppStdout (Join-Path $LogsDir "service_stdout.log")
& $NssmPath set $ServiceName AppStderr (Join-Path $LogsDir "service_stderr.log")
& $NssmPath set $ServiceName AppRotateFiles 1
& $NssmPath set $ServiceName AppRotateOnline 1
& $NssmPath set $ServiceName AppRotateBytes 10485760
& $NssmPath set $ServiceName AppExit Default Restart
& $NssmPath set $ServiceName AppThrottle 5000
& $NssmPath set $ServiceName AppRestartDelay 3000

# Variables de entorno opcionales por si .env no se carga (defensa en profundidad)
& $NssmPath set $ServiceName AppEnvironmentExtra "APP_ENV=production"

Write-Host ""
Write-Host "Iniciando servicio..." -ForegroundColor Cyan
& $NssmPath start $ServiceName

Start-Sleep -Seconds 2
$estado = & $NssmPath status $ServiceName
Write-Host ""
Write-Host "Estado del servicio '$ServiceName': $estado" -ForegroundColor Green
Write-Host ""
Write-Host "Verifique en: http://127.0.0.1:$Puerto/health" -ForegroundColor White
Write-Host "Logs en: $LogsDir\service_stdout.log / service_stderr.log" -ForegroundColor White
Write-Host ""
Write-Host "Comandos utiles:" -ForegroundColor Yellow
Write-Host "  $NssmPath restart $ServiceName"
Write-Host "  $NssmPath stop $ServiceName"
Write-Host "  $NssmPath status $ServiceName"
Write-Host "  Get-Content '$LogsDir\service_stderr.log' -Tail 50 -Wait"
