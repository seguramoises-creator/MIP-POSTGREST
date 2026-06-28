cd C:\Users\Lenovo\Proyecto\MSM\frontend
npm run build
if ($LASTEXITCODE -eq 0) {
    xcopy /E /Y dist\* C:\inetpub\wwwroot\mip\
    iisreset
    Write-Host "OK - desplegado"
} else {
    Write-Host "ERROR en build"
}
