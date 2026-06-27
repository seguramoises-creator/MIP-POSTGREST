# ===================================================================
# MSM / SCGCPR - Verificar e iniciar todos los servicios del sistema
# ===================================================================
# Uso (PowerShell como Administrador):
#   .\verificar_sistema.ps1
#
# Que hace:
#   - Revisa SQL Server Express, el servicio "MSM-Backend" (NSSM) y IIS
#   - Si alguno esta detenido, lo inicia automaticamente
#   - Prueba que el backend (API) y el sitio respondan
#   - Imprime un resumen final claro: OK o ERROR por componente
# ===================================================================

param(
    [string]$SqlServiceName    = "MSSQL`$SQLEXPRESS",
    [string]$BackendServiceName = "MSM-Backend",
    [string]$IisServiceName    = "W3SVC",
    [string]$BackendUrl        = "http://localhost:8000/api/v1/docs",
    [string]$SitioUrl          = "https://sistemamip.com"
)

$ErrorActionPreference = "Continue"
$resultados = @()

function Test-Administrador {
    $actual = [Security.Principal.WindowsIdentity]::GetCurrent()
    return (New-Object Security.Principal.WindowsPrincipal($actual)).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Asegurar-Servicio {
    param([string]$Nombre, [string]$Etiqueta)

    $svc = Get-Service -Name $Nombre -ErrorAction SilentlyContinue
    if (-not $svc) {
        Write-Host "[$Etiqueta] No se encontro el servicio '$Nombre'." -ForegroundColor Red
        return $false
    }

    if ($svc.Status -eq "Running") {
        Write-Host "[$Etiqueta] Ya estaba corriendo." -ForegroundColor Green
        return $true
    }

    Write-Host "[$Etiqueta] Detenido. Iniciando..." -ForegroundColor Yellow
    try {
        Start-Service -Name $Nombre -ErrorAction Stop
        Start-Sleep -Seconds 2
        $svc.Refresh()
        if ($svc.Status -eq "Running") {
            Write-Host "[$Etiqueta] Iniciado correctamente." -ForegroundColor Green
            return $true
        } else {
            Write-Host "[$Etiqueta] No quedo en estado Running (estado actual: $($svc.Status))." -ForegroundColor Red
            return $false
        }
    } catch {
        Write-Host "[$Etiqueta] Error al iniciar: $($_.Exception.Message)" -ForegroundColor Red
        return $false
    }
}

function Probar-Url {
    param([string]$Url, [string]$Etiqueta)
    try {
        $resp = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 10
        if ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 400) {
            Write-Host "[$Etiqueta] Responde OK ($($resp.StatusCode))." -ForegroundColor Green
            return $true
        } else {
            Write-Host "[$Etiqueta] Respondio con codigo $($resp.StatusCode)." -ForegroundColor Red
            return $false
        }
    } catch {
        Write-Host "[$Etiqueta] No responde: $($_.Exception.Message)" -ForegroundColor Red
        return $false
    }
}

Write-Host "=== MSM - Verificacion del sistema ===" -ForegroundColor Cyan

if (-not (Test-Administrador)) {
    Write-Host "AVISO: no estas en PowerShell como Administrador. Start-Service puede fallar." -ForegroundColor Yellow
}

Write-Host "`n--- Servicios de Windows ---"
$resultados += [pscustomobject]@{ Componente = "SQL Server";  OK = Asegurar-Servicio -Nombre $SqlServiceName -Etiqueta "SQL Server" }
$resultados += [pscustomobject]@{ Componente = "MSM-Backend"; OK = Asegurar-Servicio -Nombre $BackendServiceName -Etiqueta "MSM-Backend" }
$resultados += [pscustomobject]@{ Componente = "IIS (W3SVC)"; OK = Asegurar-Servicio -Nombre $IisServiceName -Etiqueta "IIS" }

Write-Host "`n--- Pruebas de conectividad ---"
if ($resultados[1].OK) {
    Start-Sleep -Seconds 2
    $resultados += [pscustomobject]@{ Componente = "Backend API"; OK = Probar-Url -Url $BackendUrl -Etiqueta "Backend API" }
} else {
    Write-Host "[Backend API] Omitido — el servicio MSM-Backend no esta corriendo." -ForegroundColor DarkYellow
    $resultados += [pscustomobject]@{ Componente = "Backend API"; OK = $false }
}

if ($resultados[2].OK) {
    $resultados += [pscustomobject]@{ Componente = "Sitio (IIS)"; OK = Probar-Url -Url $SitioUrl -Etiqueta "Sitio" }
} else {
    Write-Host "[Sitio] Omitido — IIS no esta corriendo." -ForegroundColor DarkYellow
    $resultados += [pscustomobject]@{ Componente = "Sitio (IIS)"; OK = $false }
}

Write-Host "`n=== Resumen ===" -ForegroundColor Cyan
foreach ($r in $resultados) {
    $estado = if ($r.OK) { "OK" } else { "ERROR" }
    $color  = if ($r.OK) { "Green" } else { "Red" }
    Write-Host ("{0,-15} {1}" -f $r.Componente, $estado) -ForegroundColor $color
}

if ($resultados | Where-Object { -not $_.OK }) {
    Write-Host "`nHay componentes con error. Revisa backend\logs\scgcpr.log y los mensajes arriba." -ForegroundColor Red
} else {
    Write-Host "`nTodo OK. El sistema deberia estar funcionando: $SitioUrl" -ForegroundColor Green
}
