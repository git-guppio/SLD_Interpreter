@echo off
setlocal
cd /d "%~dp0"
echo ALPHA 3 - RIMANDI TRA PAGINE / SOLO DIAGNOSTICA DOCUMENTALE
set /p BASELINE=Percorso completo del dev14c_inference.json: 
if "%BASELINE%"=="" goto errore
python -m sld_ci_v04_beta3.cross_sheet_cli --baseline-json "%BASELINE%" --out-json "reports\cross_sheet_reference_graph.json"
if errorlevel 1 goto errore
echo.
echo Report JSON e CSV in reports
pause
exit /b 0
:errore
echo ERRORE - verifica il percorso al JSON di inferenza precedente.
pause
exit /b 1
