# Alpha 17 — Diagnostica dei CAD vettoriali senza testo

**Obiettivo:** aggiungere il primo ramo geometrico di triage, **non** dichiarare risolto il riconoscimento delle gerarchie SAP su tutti gli SLD.

- Il programma continua a usare i motori Alpha 12/15/16 per le tre famiglie già riconosciute.
- Su PDF CAD **senza parole PDF native** ma ricchi di tracciati vettoriali, il programma non produce più un falso Excel a zero asset. Genera invece un report JSON, una lista CSV e anteprime PNG con regioni grafiche ripetute.
- Le regioni sono **ripetizioni grafiche non classificate**, rilevate dai colori del disegno e dalla forma approssimata: **non sono necessariamente inverter, trasformatori o String Box**. Il formato di uscita vieta di usarle direttamente come asset SAP.
- Non legge TXT di riferimento, non invia dati verso servizi esterni, non usa OCR e non modifica i PDF.
- Il confronto opzionale tra PDF segnala schemi quasi duplicati. La somiglianza visiva **non** identifica l'impianto.

## Avvio Windows

`AVVIA_SLD2HIERARCHY.bat` apre la stessa interfaccia. Selezionare PV3 o Settimo Torinese: il flusso produce un avviso e una cartella `reports/sap_alpha16/<impianto>/<data_ora>/` con `alpha17_diagnostica_geometrica.json`, `alpha17_motivi_ripetuti.csv` e `alpha17_anteprima_geometria_p1.png`.

## Avvio CLI e confronto indipendenza

```powershell
python -m sld_ci_v04_beta3.alpha17_cli --pdf "C:\...\PV13_Settimo_Torinese.pdf" --compare-pdf "C:\...\PV3.pdf" --out ".\reports\geometria_settimo"
```

## Cosa manca per il riconoscimento automatico SAP

1. Classificare semanticamente i motivi ripetuti (simbologia CU/TR/INV/SB) **senza** etichette testuali.
2. Verificare l'appartenenza padre-figlio mediante geometria e, se necessario, OCR mirato dei testi convertiti in tracciati.
3. Confrontare su SLD non duplicati con una Ground Truth indipendente, misurando precision, recall e correttezza dei parent.

**La versione non costituisce ancora un interprete universale di SLD.**

Il comando **Riepilogo prove** include anche questi PDF, riportando `NON RISOLTO` invece di `0` per gli asset non identificabili. Questa distinzione evita di presentare erroneamente uno schema incomprensibile come una CU senza inverter.
