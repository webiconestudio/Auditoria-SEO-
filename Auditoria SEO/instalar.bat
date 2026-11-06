@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Instalando dependencias...
python -m pip install -r requirements.txt
echo.
echo Listo. Para auditar una web, abre auditar.bat
pause
