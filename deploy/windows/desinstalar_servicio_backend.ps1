# ═══════════════════════════════════════════════════════════════════
# MSM / SCGCPR — Desinstalar el servicio de Windows del backend (NSSM)
# ═══════════════════════════════════════════════════════════════════
# Uso (PowerShell como Administrador):
#   .\desinstalar_servicio_backend.ps1
#   .\desinstalar_servicio_backend.ps1 -NssmPath "D:\nssm\nssm.exe"
# ═══════════════════════════════════════════════════════════════════

param(
    [string]$NssmPath    = "C:\Tools\nssm\nssm.exe",
    [string]$ServiceName = "MSM-Backend"
)

$ErrorActionPreference = "Stop"

$actual = [Security.Principal.WindowsIdentity]::GetCurrent()
$esAdmin = (New-Object Security.Principal.WindowsPrincipal($actual)).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $esAdmin) {
    Write-Host "ERROR: Este script debe ejecutarse como Administrador." -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $NssmPath)) {
    Write-Host "ERROR: No se encontró nssm.exe en: $NssmPath" -ForegroundColor Red
    exit 1
}

Write-Host "Deteniendo servicio '$ServiceName'..." -ForegroundColor Yellow
& $NssmPath stop $ServiceName

Write-Host "Eliminando servicio '$ServiceName'..." -ForegroundColor Yellow
& $NssmPath remove $ServiceName confirm

Write-Host "Listo. Servicio '$ServiceName' eliminado." -ForegroundColor Green
