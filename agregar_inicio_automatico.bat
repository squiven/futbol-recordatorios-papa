@echo off
setlocal
set "carpeta=%~dp0"
if "%carpeta:~-1%"=="\" set "carpeta=%carpeta:~0,-1%"
set "destino=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\FutbolYRecordatorios.vbs"

> "%destino%" echo Set objShell = CreateObject("WScript.Shell")
>> "%destino%" echo objShell.CurrentDirectory = "%carpeta%"
>> "%destino%" echo objShell.Run "pythonw.exe " ^& Chr(34) ^& "%carpeta%\app.py" ^& Chr(34), 0, False

echo.
echo Listo! Futbol y Recordatorios va a arrancar solo, sin ventanas, la
echo proxima vez que se prenda la computadora.
echo.
echo (Si en algun momento queres desactivarlo, corre "quitar_inicio_automatico.bat")
pause
