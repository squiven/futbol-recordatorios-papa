@echo off
echo ============================================
echo   Desinstalar Futbol y Recordatorios
echo ============================================
echo.
echo Paso 1: sacando el inicio automatico de Windows (si estaba activado)...
set "destino=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\FutbolYRecordatorios.vbs"
if exist "%destino%" (
    del "%destino%"
    echo   Listo, ya no arranca solo con Windows.
) else (
    echo   No estaba activado, no hace falta hacer nada.
)

echo.
echo Paso 2: cerrando el programa si esta corriendo...
taskkill /F /IM pythonw.exe /FI "WINDOWTITLE eq *" >nul 2>&1
wmic process where "name='pythonw.exe' and CommandLine like '%%app.py%%'" delete >nul 2>&1

echo.
echo ============================================
echo Listo. Ahora falta un ultimo paso manual:
echo borrar esta carpeta completa (FutbolYRecordatorios)
echo desde el Explorador de Windows.
echo ============================================
echo.
pause
