@echo off
cd /d "%~dp0"
echo BOOTSTRAP 5 - ROI automatica da ETICHETTA UNIVOCA (sola lettura)
echo Percorso completo del file PDF (non la cartella), senza virgolette:
set /p PDF=PDF: 
if not exist "%PDF%" (
  echo ERRORE: file PDF non trovato.
  pause
  exit /b 1
)
echo Esempi: CABINA 7 oppure IBR-TPO-01-01
set /p TAG=ETICHETTA: 
python -m sld_ci_v04_beta3.integration_cli --pdf "%PDF%" --page 1 --auto-roi-tag "%TAG%" --roi-padding 65 --out "reports\semantic_bridge_local.json"
if errorlevel 1 (
  echo ERRORE: etichetta assente o non univoca, oppure problema di lettura. Non e' stata scelta una istanza a caso.
  pause
  exit /b 1
)
echo Report: reports\semantic_bridge_local.json
pause
