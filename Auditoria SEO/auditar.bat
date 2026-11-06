@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
set "SERANKING_API_KEY=89c7f4d4-1b9c-5735-2c7a-c96d94928153"
python auditoria.py %*
echo.
pause