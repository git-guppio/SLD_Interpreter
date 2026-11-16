@echo off
setlocal
cd /d "%~dp0"
echo ALPHA 12 - SELEZIONE PDF CON FINESTRA WINDOWS
python -m sld_ci_v04_beta3.sap_picker_gui
set "RESULT=%ERRORLEVEL%"
if not "%RESULT%"=="0" echo [ERRORE] La procedura non e stata completata. Vedi i dettagli sopra.
echo.
pause
exit /b %RESULT%
