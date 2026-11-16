@echo off
setlocal
cd /d "%~dp0"
echo Alpha 18 - Candidati vettoriali CAD (NON gerarchia SAP verificata)
set /p INPUTPDF=Percorso PDF (in alternativa usa la finestra del Workbench): 
if not exist "%INPUTPDF%" (
  echo [ERRORE] PDF non trovato: %INPUTPDF%
  pause
  exit /b 2
)
set /p OUTDIR=Cartella destinazione output (es. reports\cad_alpha18): 
python -m sld_ci_v04_beta3.alpha18_cli --pdf "%INPUTPDF%" --out "%OUTDIR%"
if errorlevel 1 echo [ERRORE] Vedi messaggi precedenti.
pause
