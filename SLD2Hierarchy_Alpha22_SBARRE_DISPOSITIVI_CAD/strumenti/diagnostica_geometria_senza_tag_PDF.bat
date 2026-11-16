@echo off
setlocal
cd /d "%~dp0.."
echo ALPHA 8 - GEOMETRIA ANCHE SENZA TAG TESTUALI (solo candidati)
set /p "SLDPDF=Percorso completo del PDF SLD con estensione .pdf: "
if "%SLDPDF%"=="" goto error
if not exist "%SLDPDF%" goto error
set /p "PID=Identificativo impianto (facoltativo): "
set /p "NP=Pagine da scansionare geometricamente (INVIO = 4): "
if "%NP%"=="" set "NP=4"
python -m sld_ci_v04_beta3.geometry_first_cli --pdf "%SLDPDF%" --plant-id "%PID%" --geometry-first-pages %NP% --max-probe-pages %NP%
if errorlevel 1 goto error
echo Risultati in reports\alpha8_geometry_first.json e .csv
pause
exit /b 0
:error
echo ERRORE: controlla il nome completo PDF e il numero di pagine.
pause
exit /b 1
