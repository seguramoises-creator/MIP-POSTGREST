# ═══════════════════════════════════════════════════════════════════
# MSM / SCGCPR — Generar un JWT_SECRET_KEY fuerte para producción
# ═══════════════════════════════════════════════════════════════════
# Uso:
#   .\generar_jwt_secret.ps1
#
# Copie el valor generado a backend\.env (clave JWT_SECRET_KEY=...).
# No reutilice este valor entre entornos (dev/staging/producción).
# ═══════════════════════════════════════════════════════════════════

$bytes = New-Object byte[] 48
[System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
$secret = [Convert]::ToBase64String($bytes)

Write-Host ""
Write-Host "JWT_SECRET_KEY generado (cópielo a backend\.env):" -ForegroundColor Cyan
Write-Host ""
Write-Host $secret -ForegroundColor Green
Write-Host ""
