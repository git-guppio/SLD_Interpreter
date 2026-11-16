@echo off
setlocal DisableDelayedExpansion
cd /d "%~dp0"
echo ALPHA 10 - GERARCHIA SAP da ETICHETTE PDF (NO GROUND TRUTH)
set /p "SLD=Percorso completo del PDF SLD (con .pdf): "
set /p "PLANT=Identificativo impianto (es. PV11): "
set /p "REVIEW=JSON HITL compilato (INVIO per sola diagnostica): "
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
 python -m sld_ci_v04_beta3.sap_label_cli --sld "%SLD%" --plant-id "%PLANT%" --review-json "%REVIEW%" --out-dir "reports\sap_alpha10\%PLANT%"
) else (
 python -m sld_ci_v04_beta3.sap_label_cli --sld "%SLD%" --plant-id "%PLANT%" --out-dir "reports\sap_alpha10\%PLANT%"
)
if errorlevel 1 echo [ERRORE] La diagnostica Alpha 10 non e' riuscita.
pause
endlocal
