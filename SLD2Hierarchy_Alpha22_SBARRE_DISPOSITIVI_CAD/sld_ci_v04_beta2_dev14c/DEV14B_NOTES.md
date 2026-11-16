# DEV14B NOTES

Patch UX di dev14: nessuna modifica alla logica elettrica.

- avanzamento visibile durante ogni analisi e ricalcolo automatico;
- percentuale stimata basata sulle pagine processate, con fase finale separata;
- heartbeat ogni 2 secondi con tempo trascorso, cosi l'operatore distingue un calcolo lungo da un processo fermo;
- il dettaglio tecnico continua a essere scritto solo nel log.

La percentuale e' volutamente indicata come avanzamento operativo, non come stima temporale esatta.
