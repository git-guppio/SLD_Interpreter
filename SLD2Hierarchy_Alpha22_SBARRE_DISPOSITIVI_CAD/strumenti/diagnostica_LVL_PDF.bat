@echo off
setlocal
cd /d "%~dp0.."
echo Alpha16 - Diagnostica etichette LVL-SB, inverter, TR candidati
set /p "PDF=Percorso PDF completo: "
set /p "PLANT=Identificativo impianto: "
python -m sld_ci_v04_beta3.alpha16_cli --pdf "%PDF%" --plant-id "%PLANT%" --out "reports\alpha16_diagnostica_manual\%PLANT%"
pause
