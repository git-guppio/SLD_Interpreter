# Alpha 13 — verifica visiva delle evidenze PDF

## Obiettivo

La diagnostica Alpha 12 resta invariata. Alpha 13 aggiunge una **finestra di verifica** per ogni inverter: mostra un ritaglio del PDF originale con tre evidenziazioni: **TR** (blu), **INV** (arancione), **quantità String Box** (viola). Le coordinate provengono dalle colonne `evidenza_parent` ed `evidenza_string_box` del report esistente. Le evidenziazioni indicano **etichette**, non un tracciamento automatico dei collegamenti elettrici.

## Uso su Windows

1. Conserva Alpha 12 GUI nella sua cartella; decomprimi questo ZIP **in una nuova cartella**.
2. Per un SLD già analizzato da Alpha 12 esegui `AVVIA_VERIFICA_VISIVA_ALPHA13.bat`. Si aprono due finestre di selezione: scegli la **cartella dei risultati Alpha 12** (quella che contiene `alpha12_riepilogo.json`) e poi il **PDF originale** corrispondente. Puoi usare i report creati dalla precedente Alpha 12 GUI: non devi ripetere l'analisi.
3. Nella finestra scegli un inverter dalla tabella a sinistra. Il ritaglio con le etichette evidenziate appare a destra.
4. Se hai verificato il parent e la quantità indicata, usa **Conferma dati visualizzati**, poi conferma la domanda. Ogni pressione riguarda **solo quell'inverter**, mai tutte le CU.
5. Se vedi una discrepanza, usa **Da correggere** e scrivi una nota concreta. Il software **non applica automaticamente alcuna correzione** né altera l'Excel o il PDF.
6. Puoi usare **Annulla verifica** sulla riga selezionata. Tutte le decisioni sono salvate immediatamente in una copia separata dei risultati.

In alternativa puoi avviare `AVVIA_ALPHA12_CON_FINESTRA.bat` per eseguire una nuova estrazione e poi aprire la verifica visiva quando richiesto.

## File prodotti

Nella cartella del report selezionato:

- `alpha13_operator_review_APPROVED.json` — JSON HITL compatibile con `--review-json` di Alpha 12, con **una conferma parent per singolo inverter verificato** e, in un campo separato `alpha13_visual_checks`, i controlli sulle quantità String Box e le segnalazioni da correggere.
- `alpha13_registro_verifiche.csv` — registro leggibile delle decisioni con CU, TR, INV, SB, esito e note.

Solo le righe **confermate** producono `confirmed_tr_inverter_groups` nel JSON. Le righe **Da correggere** sono audit-only, senza falsi parent o quantità assegnati.

Il JSON viene mantenuto separato: per riportare le conferme parent nell'Excel di Alpha 12, rilanciare la diagnostica indicando questo file come **JSON HITL**. Per sicurezza, conservare una copia dei report prima di ricalcolare. Le conferme sulle String Box sono registrate nel JSON e nel CSV, ma non sostituiscono automaticamente eventuali quantità diverse nel PDF.

## Limiti dichiarati

- Se mancano testo/coordinate (per esempio nel PDF di Settimo Torinese), il ritaglio può non essere disponibile e la conferma congiunta viene disabilitata. Occorre una verifica manuale aggiuntiva, non un conteggio inventato.
- La corrispondenza geometrica di etichette non prova da sola l'effettiva connessione elettrica: la conferma avviene **per giudizio dell'operatore**.
- La finestra usa `tkinter` e PyMuPDF/`fitz`, già necessari all'applicazione. Il codice di analisi Alpha 12 e il motore dev14c non sono stati modificati.
- Non ci sono collegamenti cliccabili direttamente nell'Excel: per la selezione si usa il visualizzatore Alpha 13. Questa soluzione evita macro e modifiche invasive al workbook.
