# ===================================================================
# MSM / SCGCPR - Crear el sitio IIS para vista-mip.com (paso A.5)
# ===================================================================
# Que hace:
#   1. Crea (o reutiliza) un Application Pool dedicado "No Managed Code"
#   2. Crea (o reutiliza) el sitio IIS con ruta fisica = build del frontend
#      (C:\inetpub\wwwroot\mip, publicado por build_frontend_produccion.ps1)
#   3. Agrega el binding http/80 para vista-mip.com (y www.vista-mip.com)
#      - Necesario para que win-acme (Let's Encrypt) pueda validar el
#        dominio via HTTP-01 y para que la regla "Redirigir HTTP a HTTPS"
#        del web.config funcione.
#
# Lo que este script NO hace (sigue en pasos manuales):
#   - El binding https/443 y el certificado: ejecute win-acme (wacs.exe)
#     DESPUES de este script; win-acme detecta el sitio IIS recien creado
#     y crea el binding 443 + certificado automaticamente.
#
# Requisitos previos:
#   - IIS instalado, modulos ARR/URL Rewrite (configurar_iis_arr.ps1 ya
#     ejecutado), frontend publicado (build_frontend_produccion.ps1 ya
#     ejecutado) en la ruta fisica indicada.
#   - DNS de vista-mip.com (y www, si aplica) apuntando a la IP publica
#     de este servidor, y puerto 80 accesible desde Internet, ANTES de
#     ejecutar win-acme (no es requisito para este script en si).
#
# Uso (PowerShell como Administrador):
#   .\crear_sitio_iis.ps1
#   .\crear_sitio_iis.ps1 -IncluirWww:$false
# ===================================================================

param(
    [string]$SiteName       = "vista-mip.com",
    [string]$DominioPrincipal = "vista-mip.com",
    [string]$DominioWww     = "www.vista-mip.com",
    [bool]$IncluirWww       = $true,
    [string]$RutaFisica     = "C:\inetpub\wwwroot\mip",
    [string]$AppPoolName    = "MSM-Pool"
)

$ErrorActionPreference = "Stop"

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
Write-Host "  MSM - Crear sitio IIS para $SiteName" -ForegroundColor Cyan
Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host ""

Test-Administrador

Import-Module WebAdministration -ErrorAction Stop

if (-not (Test-Path $RutaFisica)) {
    Write-Host "ERROR: No existe la ruta fisica: $RutaFisica" -ForegroundColor Red
    Write-Host "Ejecute primero build_frontend_produccion.ps1 para publicar el frontend." -ForegroundColor Yellow
    exit 1
}
if (-not (Test-Path (Join-Path $RutaFisica "index.html"))) {
    Write-Host "ADVERTENCIA: no se encontro index.html en $RutaFisica (verifique el build)." -ForegroundColor Yellow
}

# 1. Application Pool ------------------------------------------------------
Write-Host "[1/3] Configurando Application Pool '$AppPoolName' (No Managed Code)..." -ForegroundColor Yellow

if (-not (Test-Path "IIS:\AppPools\$AppPoolName")) {
    New-WebAppPool -Name $AppPoolName | Out-Null
    Write-Host "  Application Pool creado." -ForegroundColor Green
} else {
    Write-Host "  Application Pool ya existia, se reutiliza." -ForegroundColor Green
}
Set-ItemProperty "IIS:\AppPools\$AppPoolName" -Name managedRuntimeVersion -Value ""
Set-ItemProperty "IIS:\AppPools\$AppPoolName" -Name startMode -Value "AlwaysRunning"

# 2. Sitio IIS --------------------------------------------------------------
Write-Host ""
Write-Host "[2/3] Configurando sitio '$SiteName'..." -ForegroundColor Yellow

$sitioExistente = Get-Website -Name $SiteName -ErrorAction SilentlyContinue
if (-not $sitioExistente) {
    New-Website -Name $SiteName -PhysicalPath $RutaFisica -ApplicationPool $AppPoolName `
        -HostHeader $DominioPrincipal -Port 80 -Force | Out-Null
    Write-Host "  Sitio creado con binding http/80 -> $DominioPrincipal" -ForegroundColor Green
} else {
    Set-ItemProperty "IIS:\Sites\$SiteName" -Name physicalPath -Value $RutaFisica
    Set-ItemProperty "IIS:\Sites\$SiteName" -Name applicationPool -Value $AppPoolName
    Write-Host "  Sitio ya existia; ruta fisica y app pool actualizados." -ForegroundColor Green
}

# 3. Binding adicional para www (opcional) -----------------------------------
Write-Host ""
Write-Host "[3/3] Verificando binding para www..." -ForegroundColor Yellow

if ($IncluirWww) {
    $bindingsActuales = Get-WebBinding -Name $SiteName
    $tieneWww = $bindingsActuales | Where-Object { $_.bindingInformation -like "*$DominioWww*" }
    if (-not $tieneWww) {
        New-WebBinding -Name $SiteName -Protocol http -Port 80 -HostHeader $DominioWww
        Write-Host "  Binding http/80 -> $DominioWww agregado." -ForegroundColor Green
    } else {
        Write-Host "  Binding para $DominioWww ya existia." -ForegroundColor Green
    }
} else {
    Write-Host "  Omitido (-IncluirWww:`$false)." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Listo. Bindings actuales del sitio '$SiteName':" -ForegroundColor Cyan
Get-WebBinding -Name $SiteName | Format-Table protocol, bindingInformation -AutoSize

Write-Host ""
Write-Host "Siguiente paso (certificado Let's Encrypt via win-acme):" -ForegroundColor Yellow
Write-Host "  1. Verifique DNS:  nslookup $DominioPrincipal   (debe apuntar a la IP publica de este servidor)" -ForegroundColor White
Write-Host "  2. Confirme que el puerto 80 es accesible desde Internet (firewall/router)." -ForegroundColor White
Write-Host "  3. Descargue win-acme (wacs.exe) desde https://www.win-acme.com/ y ejecutelo" -ForegroundColor White
Write-Host "     como Administrador. Elija 'N: Create certificate', fuente 'IIS', y" -ForegroundColor White
Write-Host "     seleccione el sitio '$SiteName'. win-acme creara el binding https/443" -ForegroundColor White
Write-Host "     y configurara la renovacion automatica." -ForegroundColor White
