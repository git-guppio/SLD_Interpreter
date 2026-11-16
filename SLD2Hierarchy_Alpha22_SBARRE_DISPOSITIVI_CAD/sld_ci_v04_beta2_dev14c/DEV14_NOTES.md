# DEV14 — semplificazione del flusso operatore

Dev14 non modifica l'algoritmo di interpretazione introdotto fino a dev13. Introduce uno strato operativo semplificato:

- un solo comando per CASE: `python -m sld_ci_v04_beta2_dev14c.workflow --case <CASE_DIR>`;
- rilevamento automatico di `*_SLD.pdf`, `*_LAYOUT.pdf`, output, knowledge store e feedback;
- recupero automatico dell'ultimo feedback valido se il feedback canonico non esiste;
- output console sintetico; il dettaglio completo va in `*_dev14_full.log`;
- GUI automatica solo quando serve;
- GUI con una sola richiesta per volta e senza comandi tecnici/pattern/bridge nel flusso normale;
- dopo una risposta dell'operatore, l'analisi viene rilanciata automaticamente e viene mostrato un nuovo riepilogo.

Obiettivo: l'operatore deve rispondere a una domanda visiva, non conoscere l'architettura interna del motore.
