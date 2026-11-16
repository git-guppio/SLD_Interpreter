@echo off
setlocal
cd /d "%~dp0"
echo Alpha 20 - Tracce continue CAD verso i morsetti di ingresso
set /p INPUTPDF=Percorso PDF CAD: 
if not exist "%INPUTPDF%" (
 echo [ERRORE] PDF non trovato.
 pause
 exit /b 2
)
set /p OUTDIR=Cartella risultati (INVIO = reports\cad_alpha20): 
if "%OUTDIR%"=="" set "OUTDIR=reports\cad_alpha20"
python -m sld_ci_v04_beta3.alpha20_cli --pdf "%INPUTPDF%" --out "%OUTDIR%"
if errorlevel 1 echo [ERRORE] Analisi incompleta.
pause
