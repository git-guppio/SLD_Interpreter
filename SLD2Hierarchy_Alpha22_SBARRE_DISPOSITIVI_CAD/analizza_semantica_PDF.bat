@echo off
cd /d "%~dp0"
echo BOOTSTRAP 5 - Analisi semantica + geometrica (sola lettura)
echo Percorso COMPLETO del PDF (deve finire con .pdf), senza virgolette:
set /p PDF=PDF: 
if not exist "%PDF%" (
  echo ERRORE: File non trovato. Indicare un file PDF, non una cartella.
  pause
  exit /b 1
)
python -m sld_ci_v04_beta3.integration_cli --pdf "%PDF%" --page 1 --out "reports\semantic_bridge.json"
if errorlevel 1 (
  echo ERRORE: elaborazione non completata.
  pause
  exit /b 1
)
echo Il report si trova in reports\semantic_bridge.json
pause
