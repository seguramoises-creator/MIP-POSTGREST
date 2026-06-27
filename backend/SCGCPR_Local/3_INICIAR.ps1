# ═══════════════════════════════════════════════════════════════════
# SCGCPR — Iniciar servidor FastAPI
# ═══════════════════════════════════════════════════════════════════
Write-Host ""
Write-Host "Iniciando SCGCPR..." -ForegroundColor Cyan
Write-Host "API:    http://localhost:8000/api/v1/docs" -ForegroundColor White
Write-Host "Health: http://localhost:8000/health" -ForegroundColor White
Write-Host "Ctrl+C para detener`n" -ForegroundColor Yellow

Set-Location backend
& "venv\Scripts\Activate.ps1"
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
