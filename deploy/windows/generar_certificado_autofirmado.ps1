# ===================================================================
# MSM / SCGCPR - Certificado TLS autofirmado para vista-mip.com
# ===================================================================
# Que hace:
#   1. Genera un certificado autofirmado (valido 2 anios) para
#      vista-mip.com y www.vista-mip.com en el almacen de certificados
#      de la maquina local (LocalMachine\My).
#   2. Crea (o reemplaza) los bindings https/443 del sitio IIS indicado,
#      usando SNI, y les asocia el certificado generado.
#
# IMPORTANTE - uso de un certificado autofirmado:
#   - Los navegadores mostraran una advertencia "conexion no segura /
#     certificado no confiable" porque no esta firmado por una autoridad
#     certificadora (CA) publica. Esto es normal y esperado para pruebas
#     internas. Para produccion real, reemplazar mas adelante por un
#     certificado de Let's Encrypt (win-acme) u otra CA, una vez el
#     dominio vista-mip.com tenga DNS publico resuelto.
#   - Este script NO requiere DNS ni acceso a Internet, solo se ejecuta
#     localmente en el servidor.
#
# Requisitos previos:
#   - Sitio IIS ya creado (ver crear_sitio_iis.ps1).
#
# Uso (PowerShell como Administrador):
#   .\generar_certificado_autofirmado.ps1
# ===================================================================

param(
    [string]$SiteName         = "vista-mip.com",
    [string]$DominioPrincipal = "vista-mip.com",
    [string]$DominioWww       = "www.vista-mip.com",
    [bool]$IncluirWww         = $true,
    [int]$AniosValidez        = 2
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
Write-Host "  MSM - Certificado TLS autofirmado para $DominioPrincipal" -ForegroundColor Cyan
Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host ""

Test-Administrador

Import-Module WebAdministration -ErrorAction Stop

$sitio = Get-Website -Name $SiteName -ErrorAction SilentlyContinue
if (-not $sitio) {
    Write-Host "ERROR: No existe el sitio IIS '$SiteName'. Ejecute primero crear_sitio_iis.ps1." -ForegroundColor Red
    exit 1
}

$nombresDns = @($DominioPrincipal)
if ($IncluirWww) { $nombresDns += $DominioWww }

# 1. Generar certificado autofirmado -----------------------------------------
Write-Host "[1/3] Generando certificado autofirmado para: $($nombresDns -join ', ')" -ForegroundColor Yellow

$cert = New-SelfSignedCertificate `
    -DnsName $nombresDns `
    -CertStoreLocation "cert:\LocalMachine\My" `
    -FriendlyName "MSM $DominioPrincipal (autofirmado)" `
    -NotAfter (Get-Date).AddYears($AniosValidez) `
    -KeyExportPolicy Exportable `
    -KeySpec KeyExchange `
    -KeyLength 2048 `
    -HashAlgorithm SHA256

$thumbprint = $cert.Thumbprint
Write-Host "  Certificado creado. Thumbprint: $thumbprint" -ForegroundColor Green

# 2. Confiar en el certificado localmente (Trusted Root) ---------------------
# Esto evita la advertencia del navegador SOLO en este equipo. En otros
# equipos que visiten el sitio, la advertencia seguira apareciendo
# (comportamiento esperado de un certificado autofirmado).
Write-Host ""
Write-Host "[2/3] Agregando el certificado a 'Entidades de certificacion raiz de confianza' (este equipo)..." -ForegroundColor Yellow
$origen = Get-Item "cert:\LocalMachine\My\$thumbprint"
$almacenRaiz = New-Object System.Security.Cryptography.X509Certificates.X509Store("Root", "LocalMachine")
$almacenRaiz.Open("ReadWrite")
$almacenRaiz.Add($origen)
$almacenRaiz.Close()
Write-Host "  Listo." -ForegroundColor Green

# 3. Bindings https/443 ------------------------------------------------------
Write-Host ""
Write-Host "[3/3] Configurando bindings https/443 con SNI..." -ForegroundColor Yellow

foreach ($host_ in $nombresDns) {
    $existente = Get-WebBinding -Name $SiteName -Protocol https | Where-Object { $_.bindingInformation -like "*$host_*" }
    if ($existente) {
        Write-Host "  Eliminando binding https previo para $host_..." -ForegroundColor Cyan
        Remove-WebBinding -Name $SiteName -Protocol https -HostHeader $host_ -Port 443
    }
    New-WebBinding -Name $SiteName -Protocol https -Port 443 -HostHeader $host_ -SslFlags 1
    Write-Host "  Binding https/443 -> $host_ creado." -ForegroundColor Green

    $binding = Get-WebBinding -Name $SiteName -Protocol https -HostHeader $host_ -Port 443
    $binding.AddSslCertificate($thumbprint, "my")
    Write-Host "  Certificado asociado a $host_." -ForegroundColor Green
}

Write-Host ""
Write-Host "Listo. Bindings actuales del sitio '$SiteName':" -ForegroundColor Cyan
Get-WebBinding -Name $SiteName | Format-Table protocol, bindingInformation -AutoSize

Write-Host ""
Write-Host "Pruebe en este mismo servidor:" -ForegroundColor Yellow
Write-Host "  https://$DominioPrincipal/health   (puede requerir agregar una entrada en C:\Windows\System32\drivers\etc\hosts" -ForegroundColor White
Write-Host "   apuntando $DominioPrincipal a 127.0.0.1, ya que el DNS publico todavia no existe)" -ForegroundColor White
Write-Host ""
Write-Host "Recuerde: este certificado es autofirmado. Cuando el dominio tenga DNS publico," -ForegroundColor Yellow
Write-Host "reemplacelo por uno de Let's Encrypt (ver crear_sitio_iis.ps1 + win-acme)." -ForegroundColor Yellow
