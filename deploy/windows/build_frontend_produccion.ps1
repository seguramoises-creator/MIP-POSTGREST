# ═══════════════════════════════════════════════════════════════════
# MSM / SCGCPR — Build de producción del frontend + publicación en IIS
# ═══════════════════════════════════════════════════════════════════
# Qué hace:
#   1. Escribe frontend\.env.production con VITE_API_URL=https://vista-mip.com/api/v1
#      (Vite carga .env.production automáticamente al ejecutar "vite build")
#   2. Ejecuta npm install (si node_modules no existe) y npm run build
#   3. Copia frontend\dist\* + deploy\windows\web.config a la carpeta del
#      sitio IIS (-DestinoIIS), por defecto C:\inetpub\wwwroot\mip
#
# Uso (PowerShell, no requiere ser Administrador salvo que -DestinoIIS
# esté bajo una carpeta protegida como C:\inetpub):
#   .\build_frontend_produccion.ps1
#   .\build_frontend_produccion.ps1 -DominioPublico "https://vista-mip.com" -DestinoIIS "D:\sitios\mip"
# ═══════════════════════════════════════════════════════════════════

param(
    [string]$ProyectoDir    = "C:\Users\Lenovo\Proyecto\MSM",
    [string]$DominioPublico = "https://vista-mip.com",
    [string]$DestinoIIS     = "C:\inetpub\wwwroot\mip"
)

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host "  MSM - Build de produccion del frontend" -ForegroundColor Cyan
Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host ""

$FrontendDir = Join-Path $ProyectoDir "frontend"
if (-not (Test-Path $FrontendDir)) {
    Write-Host "ERROR: No se encontró la carpeta frontend en $ProyectoDir" -ForegroundColor Red
    exit 1
}

# 1. Variable de entorno de build -----------------------------------------
$envProdPath = Join-Path $FrontendDir ".env.production"
$apiUrl = "$DominioPublico/api/v1"
Write-Host "[1/3] Escribiendo $envProdPath con VITE_API_URL=$apiUrl" -ForegroundColor Yellow
"VITE_API_URL=$apiUrl" | Set-Content -Path $envProdPath -Encoding UTF8

# 2. Instalar dependencias y compilar --------------------------------------
Write-Host ""
Write-Host "[2/3] Compilando frontend (npm run build)..." -ForegroundColor Yellow
Push-Location $FrontendDir
try {
    if (-not (Test-Path (Join-Path $FrontendDir "node_modules"))) {
        Write-Host "  node_modules no existe, ejecutando npm install..." -ForegroundColor Cyan
        npm install
        if ($LASTEXITCODE -ne 0) { throw "npm install falló" }
    }

    npm run build
    if ($LASTEXITCODE -ne 0) { throw "npm run build falló" }
}
finally {
    Pop-Location
}

$DistDir = Join-Path $FrontendDir "dist"
if (-not (Test-Path (Join-Path $DistDir "index.html"))) {
    Write-Host "ERROR: el build no generó dist\index.html. Revise la salida de npm run build." -ForegroundColor Red
    exit 1
}

# 3. Publicar en la carpeta del sitio IIS -----------------------------------
Write-Host ""
Write-Host "[3/3] Publicando en $DestinoIIS ..." -ForegroundColor Yellow
New-Item -ItemType Directory -Force -Path $DestinoIIS | Out-Null

# Limpiar contenido previo (conserva la carpeta en sí, por permisos de IIS)
Get-ChildItem -Path $DestinoIIS -Force | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

Copy-Item -Path (Join-Path $DistDir "*") -Destination $DestinoIIS -Recurse -Force

$webConfigSrc = Join-Path $ProyectoDir "deploy\windows\web.config"
Copy-Item -Path $webConfigSrc -Destination (Join-Path $DestinoIIS "web.config") -Force

Write-Host ""
Write-Host "Listo. Sitio publicado en: $DestinoIIS" -ForegroundColor Green
Write-Host "VITE_API_URL usado en el build: $apiUrl" -ForegroundColor Green
Write-Host ""
Write-Host "Recuerde:" -ForegroundColor Yellow
Write-Host "  - El binding del sitio IIS debe apuntar a esta carpeta como ruta física." -ForegroundColor White
Write-Host "  - El backend debe estar corriendo en 127.0.0.1:8000 (ver instalar_servicio_backend.ps1)." -ForegroundColor White
Write-Host "  - Repita este script cada vez que cambie el código del frontend o el dominio público." -ForegroundColor White
