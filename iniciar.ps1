# MSM - Iniciar Backend + Frontend
$ROOT = "C:\Users\Lenovo\Proyecto\MSM"

Write-Host ""
Write-Host "  MSM - Iniciando servicios..." -ForegroundColor Cyan
Write-Host ""

# Backend en ventana separada
Start-Process powershell -ArgumentList "-NoExit -ExecutionPolicy Bypass -File `"$ROOT\iniciar_backend.ps1`""

Start-Sleep -Seconds 3

# Frontend en ventana separada
Start-Process powershell -ArgumentList "-NoExit -ExecutionPolicy Bypass -File `"$ROOT\iniciar_frontend.ps1`""

Start-Sleep -Seconds 3

# Abrir navegador
Start-Process "http://localhost:3000"
