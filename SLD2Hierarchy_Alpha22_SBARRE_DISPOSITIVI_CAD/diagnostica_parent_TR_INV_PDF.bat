@echo off
setlocal DisableDelayedExpansion
cd /d "%~dp0"
echo ALPHA 11 - PARENT TR / INVERTER - PROPOSTE NON VERIFICATE
set /p "SLD=Percorso completo del PDF SLD (con .pdf): "
set /p "PLANT=Identificativo impianto (es. PV11): "
set /p "REVIEW=JSON HITL approvato (INVIO per nessuna conferma): "
if not defined SLD (
 echo ERRORE: percorso PDF mancante.
 pause
 exit /b 2
)
if not defined PLANT (
 echo ERRORE: identificativo impianto mancante.
 pause
 exit /b 2
)
if defined REVIEW (
 python -m sld_ci_v04_beta3.sap_parent_cli --sld "%SLD%" --plant-id "%PLANT%" --review-json "%REVIEW%" --out-dir "reports\sap_alpha11\%PLANT%"
) else (
 python -m sld_ci_v04_beta3.sap_parent_cli --sld "%SLD%" --plant-id "%PLANT%" --out-dir "reports\sap_alpha11\%PLANT%"
)
if errorlevel 1 (
 echo [ERRORE] Elaborazione non riuscita.
 pause
 exit /b 1
)
pause
endlocal
