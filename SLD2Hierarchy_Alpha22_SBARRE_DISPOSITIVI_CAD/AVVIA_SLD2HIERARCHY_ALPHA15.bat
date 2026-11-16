@echo off
setlocal
cd /d "%~dp0"
echo SLD2Hierarchy - ALPHA 15 - RICONOSCIMENTO MULTISTILE
python -m sld_ci_v04_beta3.sap_workbench_alpha15
set "RESULT=%ERRORLEVEL%"
if not "%RESULT%"=="0" echo [ERRORE] Il workbench non si e avviato.
echo.
pause
exit /b %RESULT%
