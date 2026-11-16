@echo off
setlocal
cd /d "%~dp0.."
echo SLD2Hierarchy - ALPHA 14 - WORKBENCH SAP PV
python -m sld_ci_v04_beta3.sap_workbench_alpha14
set "RESULT=%ERRORLEVEL%"
if not "%RESULT%"=="0" echo [ERRORE] Impossibile avviare l'interfaccia. Usa AVVIA_ALPHA12_CON_FINESTRA.bat come alternativa.
echo.
pause
exit /b %RESULT%
