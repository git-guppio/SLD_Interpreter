@echo off
setlocal
cd /d "%~dp0"
echo ALPHA 7 - SIMBOLI E CONTATTI CANDIDATI (non prova continuita elettrica)
set /p SLDPDF=Percorso completo del PDF SLD: 
if "%SLDPDF%"=="" goto error
set /p PID=Identificativo impianto (facoltativo): 
set /p NP=Pagine da approfondire geometricamente (INVIO = 3): 
if "%NP%"=="" set "NP=3"
python -m sld_ci_v04_beta3.symbol_review_cli --pdf "%SLDPDF%" --plant-id "%PID%" --max-probe-pages %NP% --regions-per-page 3
if errorlevel 1 goto error
echo Report in reports\alpha7_symbol_review.json e .csv
pause
exit /b 0
:error
echo ERRORE: verificare percorso PDF e parametri della diagnostica.
pause
exit /b 1
