@echo off
setlocal
cd /d "%~dp0"
echo SLD2Hierarchy - ALPHA 22 - TOPOLOGIA CAD E TRACCIABILITA
python -m sld_ci_v04_beta3.sap_workbench_alpha16
set "RESULT=%ERRORLEVEL%"
if not "%RESULT%"=="0" echo [ERRORE] Workbench non avviato. Verifica Python, PyMuPDF e Pillow.
echo.
pause
exit /b %RESULT%
