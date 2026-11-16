@echo off
setlocal DisableDelayedExpansion
cd /d "%~dp0.."
echo ALPHA 12 - EXPORT CU TR INV STR_Box: CSV + EXCEL
set /p "SLD=Percorso completo del PDF SLD (.pdf): "
set /p "PLANT=Identificativo impianto (es. PV11_Pampa_Norte): "
set /p "REVIEW=JSON HITL approvato (INVIO per nessuno): "
if not defined SLD (
 echo [ERRORE] PDF mancante.
 pause
 exit /b 2
)
if not defined PLANT (
 echo [ERRORE] Identificativo impianto mancante.
 pause
 exit /b 2
)
if defined REVIEW (
 python -m sld_ci_v04_beta3.sap_stereotypes_cli --sld "%SLD%" --plant-id "%PLANT%" --review-json "%REVIEW%" --out-dir "reports\sap_alpha12\%PLANT%"
) else (
 python -m sld_ci_v04_beta3.sap_stereotypes_cli --sld "%SLD%" --plant-id "%PLANT%" --out-dir "reports\sap_alpha12\%PLANT%"
)
if errorlevel 1 (
 echo [ERRORE] Export Alpha 12 non riuscito.
 pause
 exit /b 1
)
echo Cartella output: reports\sap_alpha12\%PLANT%
pause
endlocal
