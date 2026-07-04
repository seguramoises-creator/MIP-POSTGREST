@echo off
echo ============================================
echo  MSM - Build y Deploy Frontend
echo ============================================
echo.

cd /d "C:\Users\Lenovo\Proyecto\MSM\frontend"

echo [1/3] Compilando TypeScript + Vite...
call npm run build
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: El build fallo. Revisa los errores arriba.
    pause
    exit /b 1
)

echo.
echo [2/3] Copiando archivos a IIS...
xcopy /E /Y "C:\Users\Lenovo\Proyecto\MSM\frontend\dist\*" "C:\inetpub\wwwroot\mip\"
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: No se pudo copiar. Ejecuta este .bat como Administrador.
    pause
    exit /b 1
)

echo.
echo [3/3] Reiniciando IIS...
iisreset /noforce
if %ERRORLEVEL% NEQ 0 (
    echo WARNING: iisreset fallo. Intenta manualmente.
)

echo.
echo ============================================
echo  Listo! Abre https://vista-mip.com
echo ============================================
pause
