@echo off
set "destino=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\FutbolYRecordatorios.vbs"

if exist "%destino%" (
    del "%destino%"
    echo Listo, el programa ya no va a arrancar solo con Windows.
) else (
    echo El inicio automatico no estaba activado.
)
pause
