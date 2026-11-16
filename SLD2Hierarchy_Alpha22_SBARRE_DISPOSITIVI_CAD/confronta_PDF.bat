@echo off
setlocal
cd /d "%~dp0"
echo CONFRONTO GEOMETRICO DEV14C VS BETA3 (sola lettura)
echo Incollare il percorso completo del PDF, senza virgolette:
set /p PDF=PDF: 
if "%PDF%"=="" (echo Nessun file indicato & pause & exit /b 1)
set "OUT=%~dp0reports\shadow_comparison.json"
if not exist "%PDF%" (echo ERRORE: il percorso deve indicare un FILE PDF, non una cartella & pause & exit /b 1)
python -m sld_ci_v04_beta3.shadow_compare --pdf "%PDF%" --pages 1 --max-strokes 1200 --out "%OUT%"
echo.
echo Il report sara' in: %OUT%
pause
