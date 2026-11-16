@echo off
setlocal
cd /d "%~dp0.."
echo DIAGNOSTICA GEOMETRICA IN AREA - NON E' ANALISI DI TUTTA LA PAGINA
set /p PDF=Incolla percorso completo PDF: 
if not exist "%PDF%" (echo ERRORE: file PDF non trovato & pause & exit /b 1)
set /p AREA=Coordinate area PDF in punti [x0 y0 x1 y1], es. 0 0 250 250: 
if "%AREA%"=="" (echo ERRORE: specificare coordinate & pause & exit /b 1)
python -m sld_ci_v04_beta3.shadow_compare --pdf "%PDF%" --pages 1 --max-strokes 1200 --roi %AREA% --out "%~dp0reports\area_comparison.json"
if errorlevel 1 (echo ERRORE - controlla le coordinate & pause & exit /b 1)
echo Report area: %~dp0reports\area_comparison.json
pause
