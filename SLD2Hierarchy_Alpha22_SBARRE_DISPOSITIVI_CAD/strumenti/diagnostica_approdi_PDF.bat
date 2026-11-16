@echo off
setlocal
cd /d "%~dp0.."
echo ALPHA 4 - APPRODI RIMANDI SU VETTORI SLD (diagnostica, non verifica elettrica)
set /p BASELINE=Percorso del dev14c_inference.json: 
if "%BASELINE%"=="" goto errore
set /p SLDPDF=Percorso del PDF SLD corrispondente: 
if "%SLDPDF%"=="" goto errore
set /p PAGES=Campione pagine (es. 1,2,4), oppure INVIO per tutte: 
if "%PAGES%"=="" (
 python -m sld_ci_v04_beta3.reference_landings_cli --baseline-json "%BASELINE%" --sld-pdf "%SLDPDF%"
) else (
 python -m sld_ci_v04_beta3.reference_landings_cli --baseline-json "%BASELINE%" --sld-pdf "%SLDPDF%" --pages "%PAGES%"
)
if errorlevel 1 goto errore
echo Report in reports\reference_landings.json e .csv
pause
exit /b 0
:errore
echo ERRORE nella diagnostica degli approdi. Verifica file e impianto.
pause
exit /b 1
