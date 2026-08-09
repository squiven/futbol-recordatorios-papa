@echo off
cd /d "%~dp0"
echo Instalando/actualizando librerias necesarias...
python -m pip install -r requirements.txt --quiet
echo.
echo Arrancando Futbol y Recordatorios...
python app.py
pause
