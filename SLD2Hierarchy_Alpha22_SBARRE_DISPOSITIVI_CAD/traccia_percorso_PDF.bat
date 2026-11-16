@echo off
setlocal
cd /d "%~dp0"
echo TRACCIAMENTO GEOMETRICO CON ANCORE ESPLICITE - NON INFERENZA FEEDER
set /p PDF=Percorso completo file PDF: 
if not exist "%PDF%" (echo ERRORE: specificare un file PDF esistente & pause & exit /b 1)
set /p PAGE=Numero pagina [1]: 
if "%PAGE%"=="" set PAGE=1
set /p START=Coordinate inizio [x y] in punti PDF: 
set /p END=Coordinate fine [x y] in punti PDF: 
set /p ROI=Area opzionale [x0 y0 x1 y1] (Invio = intera pagina): 
if "%ROI%"=="" (
 python -m sld_ci_v04_beta3.path_cli --pdf "%PDF%" --page %PAGE% --start %START% --end %END% --out "%~dp0reports\path_query.json"
) else (
 python -m sld_ci_v04_beta3.path_cli --pdf "%PDF%" --page %PAGE% --start %START% --end %END% --roi %ROI% --out "%~dp0reports\path_query.json"
)
if errorlevel 1 (echo ELABORAZIONE NON COMPLETATA & pause & exit /b 1)
echo Risultato: %~dp0reports\path_query.json
pause
