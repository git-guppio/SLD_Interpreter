@echo off
setlocal
cd /d "%~dp0.."
echo Alpha 19 - Ipotesi geometriche CAD (nessun dato SAP verificato)
set /p INPUTPDF=Percorso PDF (oppure usa il selettore dell'interfaccia unica): 
if not exist "%INPUTPDF%" (
 echo [ERRORE] PDF non trovato: %INPUTPDF%
 pause
 exit /b 2
)
set /p OUTDIR=Cartella output (es. reports\cad_alpha19): 
if "%OUTDIR%"=="" set "OUTDIR=reports\cad_alpha19"
python -m sld_ci_v04_beta3.alpha19_cli --pdf "%INPUTPDF%" --out "%OUTDIR%"
if errorlevel 1 echo [ERRORE] Analisi CAD fallita.
pause
