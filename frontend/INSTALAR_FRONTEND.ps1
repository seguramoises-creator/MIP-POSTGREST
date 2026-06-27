# SCGCPR Frontend - Script de instalacion
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  SCGCPR Frontend - Instalacion" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

Write-Host "`n[>>] Verificando Node.js..." -ForegroundColor Yellow
$nodeVer = node --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "[!!] Node.js no encontrado. Instalar desde https://nodejs.org" -ForegroundColor Red
    exit 1
}
Write-Host "[OK] $nodeVer detectado" -ForegroundColor Green

Write-Host "`n[>>] Instalando dependencias npm..." -ForegroundColor Yellow
npm install
if ($LASTEXITCODE -ne 0) { Write-Host "[!!] Error instalando dependencias" -ForegroundColor Red; exit 1 }
Write-Host "[OK] Dependencias instaladas" -ForegroundColor Green

Write-Host "`n============================================================" -ForegroundColor Cyan
Write-Host "  Instalacion completa. Para iniciar el frontend:" -ForegroundColor Cyan
Write-Host "  npm run dev" -ForegroundColor White
Write-Host "  Abrir: http://localhost:3000" -ForegroundColor White
Write-Host "============================================================" -ForegroundColor Cyan
