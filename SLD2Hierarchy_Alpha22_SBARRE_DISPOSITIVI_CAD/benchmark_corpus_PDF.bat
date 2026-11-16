@echo off
setlocal
cd /d "%~dp0"
echo ALPHA 6 - BENCHMARK CORPUS SLD (no ground-truth nell'inferenza)
echo La precision/recall su asset fisici richiede annotazioni individuali validate.
set /p MAN=Percorso del manifest JSON del corpus: 
if "%MAN%"=="" goto error
python -m sld_ci_v04_beta3.corpus_cli --manifest "%MAN%"
if errorlevel 1 goto error
echo Risultati in reports\corpus_audit.json e .csv
pause
exit /b 0
:error
echo ERRORE. Controlla i percorsi PDF nel manifest.
pause
exit /b 1
