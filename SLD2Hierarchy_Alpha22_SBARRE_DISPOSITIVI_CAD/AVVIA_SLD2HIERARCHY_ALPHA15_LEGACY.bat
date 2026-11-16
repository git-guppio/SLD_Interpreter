@echo off
setlocal
cd /d "%~dp0"
python -m sld_ci_v04_beta3.sap_workbench_alpha15
pause
