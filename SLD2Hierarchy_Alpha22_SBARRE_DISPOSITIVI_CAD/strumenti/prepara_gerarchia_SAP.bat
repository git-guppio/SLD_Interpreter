@echo off
setlocal
cd /d "%~dp0.."
echo.
echo ALPHA 9 - GERARCHIA SAP / MATRIX FLOW STAGING
 echo [1] Riusa un JSON dev14c_inference esistente ^(piu rapido^)
 echo [2] Analizza un nuovo PDF SLD ^(layout facoltativo^)
set /p MODE=Scelta [1/2]: 
if "%MODE%"=="1" goto fromjson
if "%MODE%"=="2" goto frompdf
echo Scelta non valida
pause
exit /b 1
:fromjson
set /p SRC=Percorso completo dev14c_inference.json: 
if "%SRC%"=="" goto error
python -m sld_ci_v04_beta3.sap_cli --inference-json "%SRC%" --out-dir "reports\sap_alpha9"
if errorlevel 1 goto error
goto done
:frompdf
set /p SRC=Percorso completo SLD PDF ^(con .pdf^): 
if "%SRC%"=="" goto error
set /p LAYOUT=Layout PDF facoltativo ^(INVIO se assente^): 
set /p PLANT=Identificativo impianto ^(es. PV2^): 
if "%PLANT%"=="" goto error
if "%LAYOUT%"=="" (
  python -m sld_ci_v04_beta3.sap_cli --sld "%SRC%" --plant-id "%PLANT%" --ocr-mode auto --out-dir "reports\sap_alpha9"
) else (
  python -m sld_ci_v04_beta3.sap_cli --sld "%SRC%" --layout "%LAYOUT%" --plant-id "%PLANT%" --ocr-mode auto --out-dir "reports\sap_alpha9"
)
if errorlevel 1 goto error
goto done
:done
echo.
echo Completato. I file sono in reports\sap_alpha9
pause
exit /b 0
:error
echo ERRORE: verificare percorso, fonte o dati HITL
pause
exit /b 1
