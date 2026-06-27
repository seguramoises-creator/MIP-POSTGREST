Set-Location "C:\Users\Lenovo\Proyecto\MSM\backend"
Write-Host ""
Write-Host "  Backend MSM" -ForegroundColor Green
Write-Host "  API    -> http://localhost:8000/api/v1" -ForegroundColor White
Write-Host "  Swagger -> http://localhost:8000/api/v1/docs" -ForegroundColor White
Write-Host ""
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
