# ===================================================================
# MSM / SCGCPR - Configurar IIS + ARR + URL Rewrite (nivel servidor)
# ===================================================================
# Este script realiza la configuracion a NIVEL DE SERVIDOR que no puede
# definirse desde el web.config del sitio:
#   1. Habilita el rol IIS (Web-Server) si no esta instalado
#   2. Verifica que los modulos ARR y URL Rewrite esten instalados
#      (deben instalarse manualmente con los instaladores oficiales,
#      este script NO los descarga - ver enlaces abajo)
#   3. Habilita "Enable Proxy" en ARR (system.webServer/proxy)
#   4. Habilita preserveHostHeader=True - CRITICO: sin esto, IIS reescribe
#      el encabezado Host hacia 127.0.0.1:8000 y el backend (que valida
#      ALLOWED_HOSTS=["sistemamip.com",...] via TrustedHostMiddleware) rechazara
#      TODAS las peticiones con error 400.
#   5. Desbloquea la seccion system.webServer/rewrite/allowedServerVariables
#      a nivel de servidor - CRITICO: por defecto esta seccion viene
#      bloqueada (overrideModeDefault=Deny) y el web.config del sitio
#      (que usa <allowedServerVariables> para reenviar X-Forwarded-*)
#      falla con HTTP 500.52 "This configuration section cannot be used
#      at this path" hasta que se desbloquea aqui.
#
# Ejecutar como Administrador, UNA SOLA VEZ por servidor.
# ===================================================================

$ErrorActionPreference = "Stop"

$actual = [Security.Principal.WindowsIdentity]::GetCurrent()
$esAdmin = (New-Object Security.Principal.WindowsPrincipal($actual)).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $esAdmin) {
    Write-Host "ERROR: Ejecute este script como Administrador." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host "  MSM - Configuracion de IIS + ARR + URL Rewrite" -ForegroundColor Cyan
Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host ""

# 1. Rol IIS ------------------------------------------------------------
Write-Host "[1/5] Verificando rol Web-Server (IIS)..." -ForegroundColor Yellow

$tieneServerManager = $null -ne (Get-Command Get-WindowsFeature -ErrorAction SilentlyContinue)

if ($tieneServerManager) {
    # Windows Server: usar Server Manager (DISM via ServerManager module)
    $feature = Get-WindowsFeature -Name Web-Server -ErrorAction SilentlyContinue
    if ($feature -and -not $feature.Installed) {
        Write-Host "Instalando rol IIS (Web-Server) con sub-caracteristicas comunes..." -ForegroundColor Cyan
        Install-WindowsFeature -Name Web-Server, Web-Static-Content, Web-Http-Redirect, `
            Web-Http-Logging, Web-Request-Monitor, Web-Filtering, Web-Stat-Compression `
            -IncludeManagementTools
    } else {
        Write-Host "IIS ya esta instalado." -ForegroundColor Green
    }
} else {
    # Windows 10/11 (cliente): Get-WindowsFeature no existe; usar Windows Optional Features
    Write-Host "Equipo con Windows cliente (no Server) - usando Get-WindowsOptionalFeature..." -ForegroundColor Yellow
    try {
        $iisFeature = Get-WindowsOptionalFeature -Online -FeatureName IIS-WebServerRole -ErrorAction Stop
        if ($iisFeature.State -ne "Enabled") {
            Write-Host "Habilitando IIS (rol y componentes comunes)..." -ForegroundColor Cyan
            Enable-WindowsOptionalFeature -Online -NoRestart -All -FeatureName `
                IIS-WebServerRole, IIS-WebServer, IIS-CommonHttpFeatures, IIS-HttpErrors, `
                IIS-HttpLogging, IIS-RequestFiltering, IIS-StaticContent, IIS-DefaultDocument, `
                IIS-HttpRedirect, IIS-ManagementConsole | Out-Null
            Write-Host "IIS habilitado." -ForegroundColor Green
        } else {
            Write-Host "IIS ya esta instalado." -ForegroundColor Green
        }
    } catch {
        Write-Host "No se pudo verificar/instalar IIS automaticamente: $($_.Exception.Message)" -ForegroundColor Yellow
        Write-Host "Verifique manualmente en: Panel de Control > Programas > Activar o desactivar las caracteristicas de Windows > Internet Information Services" -ForegroundColor Yellow
    }
}

# 2. Verificar ARR y URL Rewrite -----------------------------------------
Write-Host ""
Write-Host "[2/5] Verificando modulos ARR y URL Rewrite..." -ForegroundColor Yellow

$rutasArr = @(
    "$env:SystemRoot\System32\inetsrv\requestRouter.dll",
    "$env:ProgramFiles\IIS\Application Request Routing\requestRouter.dll",
    "${env:ProgramFiles(x86)}\IIS\Application Request Routing\requestRouter.dll"
)
$arrInstalado = $false
foreach ($ruta in $rutasArr) {
    if ($ruta -and (Test-Path $ruta)) { $arrInstalado = $true; break }
}

$rewriteInstalado = Test-Path "$env:SystemRoot\System32\inetsrv\rewrite.dll"

if (-not $arrInstalado) {
    Write-Host "  Application Request Routing (ARR) NO esta instalado." -ForegroundColor Red
    Write-Host "  Descargue e instale desde:" -ForegroundColor Yellow
    Write-Host "  https://www.iis.net/downloads/microsoft/application-request-routing" -ForegroundColor White
} else {
    Write-Host "  ARR: instalado." -ForegroundColor Green
}

if (-not $rewriteInstalado) {
    Write-Host "  URL Rewrite Module NO esta instalado." -ForegroundColor Red
    Write-Host "  Descargue e instale desde:" -ForegroundColor Yellow
    Write-Host "  https://www.iis.net/downloads/microsoft/url-rewrite" -ForegroundColor White
} else {
    Write-Host "  URL Rewrite: instalado." -ForegroundColor Green
}

if (-not $arrInstalado -or -not $rewriteInstalado) {
    Write-Host ""
    Write-Host "Instale los modulos faltantes y vuelva a ejecutar este script." -ForegroundColor Red
    exit 1
}

# 3. Habilitar el proxy de ARR a nivel de servidor -----------------------
Write-Host ""
Write-Host "[3/5] Habilitando 'Enable Proxy' en ARR (system.webServer/proxy)..." -ForegroundColor Yellow

$appcmd = "$env:SystemRoot\System32\inetsrv\appcmd.exe"

& $appcmd set config -section:system.webServer/proxy /enabled:"True" /commit:apphost
& $appcmd set config -section:system.webServer/proxy /preserveHostHeader:"True" /commit:apphost

Write-Host "  Proxy habilitado y preserveHostHeader=True." -ForegroundColor Green
Write-Host "  (preserveHostHeader es CRITICO: permite que el backend reciba" -ForegroundColor Green
Write-Host "   Host: sistemamip.com en lugar de 127.0.0.1:8000, requerido por ALLOWED_HOSTS)" -ForegroundColor Green

# 4. Desbloquear allowedServerVariables (evita HTTP 500.52) ---------------
Write-Host ""
Write-Host "[4/5] Desbloqueando system.webServer/rewrite/allowedServerVariables..." -ForegroundColor Yellow

& $appcmd unlock config -section:system.webServer/rewrite/allowedServerVariables

Write-Host "  Seccion desbloqueada." -ForegroundColor Green
Write-Host "  (sin esto, el web.config del sitio falla con HTTP 500.52 al usar" -ForegroundColor Green
Write-Host "   <allowedServerVariables> para reenviar X-Forwarded-Host/Proto/For)" -ForegroundColor Green

# 5. Verificacion ---------------------------------------------------------
Write-Host ""
Write-Host "[5/5] Verificando configuracion aplicada..." -ForegroundColor Yellow
& $appcmd list config -section:system.webServer/proxy

Write-Host ""
Write-Host "Listo. Continue con la creacion del sitio en IIS Manager y copie" -ForegroundColor Cyan
Write-Host "deploy\windows\web.config a la raiz del sitio (junto a frontend\dist)." -ForegroundColor Cyan
