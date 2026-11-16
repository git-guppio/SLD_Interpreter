@echo off
setlocal DisableDelayedExpansion
cd /d "%~dp0.."
echo ALPHA 11 - CONFERME HUMAN-IN-THE-LOOP TR / INVERTER
set /p "PLANT=Identificativo impianto elaborato (es. PV11): "
if not defined PLANT (
 echo ERRORE: impianto mancante.
 pause
 exit /b 2
)
python -m sld_ci_v04_beta3.sap_parent_hitl_cli --proposals-json "reports\sap_alpha11\%PLANT%\alpha11_parent_proposals.json" --out "reports\sap_alpha11\%PLANT%\alpha11_operator_review_APPROVED.json"
if errorlevel 1 (
 echo [ERRORE] Creazione review non riuscita.
 pause
 exit /b 1
)
echo Ora rieseguire diagnostica_parent_TR_INV_PDF.bat fornendo il JSON APPROVED.
pause
endlocal
