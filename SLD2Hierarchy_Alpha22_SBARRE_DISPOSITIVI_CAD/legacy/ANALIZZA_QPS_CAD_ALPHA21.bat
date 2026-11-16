@echo off
setlocal
cd /d "%~dp0.."
echo SLD2Hierarchy Alpha21 - QPS CAD / String Box
set /p "PDF=Percorso completo PDF CAD: "
set /p "PLANT=Identificativo impianto (es. PV13_Settimo_Torinese): "
set /p "REVIEW=JSON conferma tecnica Alpha21 (INVIO se assente): "
for /f %%T in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set "STAMP=%%T"
set "OUT=reports\cad_alpha21\%PLANT%\%STAMP%"
if "%REVIEW%"=="" (
  python -m sld_ci_v04_beta3.alpha21_cli --pdf "%PDF%" --plant-id "%PLANT%" --out "%OUT%"
) else (
  python -m sld_ci_v04_beta3.alpha21_cli --pdf "%PDF%" --plant-id "%PLANT%" --review-json "%REVIEW%" --out "%OUT%"
)
if errorlevel 1 (
  echo [ERRORE] Verifica sorgente PDF, OCR e review; nessun successo dichiarato.
  pause
  exit /b 1
)
echo File salvati in "%OUT%"
pause
