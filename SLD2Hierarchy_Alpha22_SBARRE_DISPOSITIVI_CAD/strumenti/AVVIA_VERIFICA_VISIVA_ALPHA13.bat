@echo off
setlocal
cd /d "%~dp0.."
echo ALPHA 13 - VERIFICA VISIVA PARENT / STRING BOX
python -m sld_ci_v04_beta3.sap_visual_review_gui
set "RESULT=%ERRORLEVEL%"
if not "%RESULT%"=="0" echo [ERRORE] Controlla il dettaglio sopra.
echo.
pause
exit /b %RESULT%
