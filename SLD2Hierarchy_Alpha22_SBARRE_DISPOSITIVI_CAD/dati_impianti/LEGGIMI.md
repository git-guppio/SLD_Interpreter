# dati_impianti/

Cartella locale per i PDF di impianto reali (SLD, layout) usati per prove e
taratura. **Il contenuto è escluso da git** (vedi `.gitignore` nella radice):
solo questo file è versionato.

Struttura consigliata, una sottocartella per impianto:

```
dati_impianti/
  PV13_Settimo_Torinese/
    PV13_Settimo_Torinese.pdf
  PV3/
    PV3.pdf
```

Gli output delle analisi vanno in `reports/`, anch'essa esclusa da git.
