# DEV11E NOTES

Patch UX/validation della calibrazione feeder.

- procedura A→B resa sequenziale; B non può essere salvato prima di A;
- pulsante di salvataggio dinamico: "Conferma e salva PASSO A/B";
- messaggi espliciti dopo il clic e dopo il salvataggio;
- impossibile fallire silenziosamente il PASSO A: se manca il riferimento feeder viene mostrato un errore;
- chiusura avvisa se A/B non risultano entrambi salvati;
- feedback dello stesso tipo viene sostituito invece di accumulare duplicati involontari;
- i test del pacchetto sono stati aggiornati per importare `sld_ci_v04_beta2_dev12` e testare realmente la versione corrente.
