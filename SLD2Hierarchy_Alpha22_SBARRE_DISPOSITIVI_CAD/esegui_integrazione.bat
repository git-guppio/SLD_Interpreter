@echo off
setlocal
cd /d "%~dp0"
echo BETA3 Alpha 5 - INTEGRAZIONE SLD + LAYOUT (input sola lettura)
echo Percorso completo del PDF SLD:
set /p SLD=SLD: 
if "%SLD%"=="" goto errore
echo PDF Layout, se presente; altrimenti INVIO:
set /p LAYOUT=LAYOUT [facoltativo]: 
echo Identificativo impianto (es. PV8):
set /p PLANT=PLANT ID: 
if "%PLANT%"=="" goto errore
echo.
echo Riutilizzare il precedente dev14c_inference.json? Indicare il file o premere INVIO per una nuova inferenza.
set /p BASELINE=JSON BASELINE [facoltativo]: 
if not "%BASELINE%"=="" (
  echo Modalita baseline esistente: nessuna nuova inferenza dev14c.
  if "%LAYOUT%"=="" (
    python -m sld_ci_v04_beta3.integrated_cli --sld "%SLD%" --plant-id "%PLANT%" --baseline-json "%BASELINE%" --out-dir "reports\integrated_run"
  ) else (
    python -m sld_ci_v04_beta3.integrated_cli --sld "%SLD%" --layout "%LAYOUT%" --plant-id "%PLANT%" --baseline-json "%BASELINE%" --out-dir "reports\integrated_run"
  )
  if errorlevel 1 goto errore
  goto successo
)
echo Percorso knowledge store JSON dell'impianto, o INVIO per saltare:
set /p KNOWLEDGE=KNOWLEDGE STORE [facoltativo]: 
echo Avvio inferenza documentale completa; puo richiedere diversi minuti.
if "%LAYOUT%"=="" (
  if "%KNOWLEDGE%"=="" (
    python -m sld_ci_v04_beta3.integrated_cli --sld "%SLD%" --plant-id "%PLANT%" --out-dir "reports\integrated_run"
  ) else (
    python -m sld_ci_v04_beta3.integrated_cli --sld "%SLD%" --plant-id "%PLANT%" --knowledge-store "%KNOWLEDGE%" --out-dir "reports\integrated_run"
  )
) else (
  if "%KNOWLEDGE%"=="" (
    python -m sld_ci_v04_beta3.integrated_cli --sld "%SLD%" --layout "%LAYOUT%" --plant-id "%PLANT%" --out-dir "reports\integrated_run"
  ) else (
    python -m sld_ci_v04_beta3.integrated_cli --sld "%SLD%" --layout "%LAYOUT%" --plant-id "%PLANT%" --knowledge-store "%KNOWLEDGE%" --out-dir "reports\integrated_run"
  )
)
if errorlevel 1 goto errore
:successo
echo.
echo Report prodotti in reports\integrated_run
pause
exit /b 0
:errore
echo ERRORE: controlla i percorsi PDF/JSON, lo scope PLANT e il log.
pause
exit /b 1
