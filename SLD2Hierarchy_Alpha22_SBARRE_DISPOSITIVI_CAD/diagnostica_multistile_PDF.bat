@echo off
setlocal
cd /d "%~dp0"
echo ALPHA 7 - TRIAGE MULTISTILE SLD (documentale + aree vettoriali candidate)
set /p SLDPDF=Percorso PDF SLD da analizzare: 
if "%SLDPDF%"=="" goto error
set /p PID=Identificativo impianto (facoltativo): 
set /p OCR=Eseguire OCR di anteprima sulla prima pagina senza testo? [s/N]: 
if /i "%OCR%"=="s" (
  python -m sld_ci_v04_beta3.multistyle_cli --pdf "%SLDPDF%" --plant-id "%PID%" --ocr-preview
) else (
  python -m sld_ci_v04_beta3.multistyle_cli --pdf "%SLDPDF%" --plant-id "%PID%"
)
if errorlevel 1 goto error
echo Report in reports\multistyle_preflight.json e .csv
pause
exit /b 0
:error
echo ERRORE nella diagnostica. Verifica il PDF e gli eventuali requisiti OCR.
pause
exit /b 1
