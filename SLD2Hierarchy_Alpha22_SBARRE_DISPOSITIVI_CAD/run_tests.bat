@echo off
setlocal
cd /d "%~dp0"
python prepara_fixture_test.py
if errorlevel 1 (
  echo ERRORE nella preparazione dei PDF di test. Nessun test eseguito.
  pause
  exit /b 1
)
python -m unittest discover -s sld_ci_v04_beta3/tests -v
if errorlevel 1 (
  echo ERRORE nei test beta3
  pause
  exit /b 1
)
python -m unittest discover -s sld_ci_v04_beta2_dev14c/tests -v
if errorlevel 1 (
  echo ERRORE nei test dev14c
  pause
  exit /b 1
)
echo TEST COMPLETATI - 434/434 attesi
pause
