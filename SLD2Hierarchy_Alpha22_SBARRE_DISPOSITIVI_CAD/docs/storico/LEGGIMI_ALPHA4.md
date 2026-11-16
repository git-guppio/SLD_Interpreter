# SLD2Hierarchy — Integrated Alpha 4 (diagnostica approdi)

**Scopo limitato:** associare i rimandi *reciproci già documentati* agli eventuali segmenti vettoriali solidi nelle immediate vicinanze della loro etichetta, e cercare testo nativo «CELDA DE … LINEA» nell’area. Nessun risultato viene promosso a verifica di terminale, attraversamento di cella o feeder–CU.

## Validazioni

- Suite: `run_tests.bat` — attesi 89 test beta3 e 49 dev14c, 138 in totale.
- Verifica vettoriale campione PV8 reale sulle pagine 1, 2 e 4: 6 estremi dei rimandi esaminati, 6 con un singolo segmento vettoriale candidato e un riferimento testuale locale di cella linea. **Sono 6 casi campionati, non 94 estremi completamente verificati**.
- Verifica identità dell’input: stesso nome file PDF SLD e stesso numero pagine dichiarati nel baseline. Non vengono confrontati hash PDF byte-per-byte. Non impiega Ground Truth né conteggi attesi.
- `sld_ci_v04_beta2_dev14c` non modificato.

## Esecuzione Windows

1. Estrai il nuovo ZIP in una cartella distinta sotto `prototype`.
2. Facoltativo: `cmd /k ".\run_tests.bat"`.
3. Per la diagnostica usa `cmd /k ".\diagnostica_approdi_PDF.bat"`.
4. Quando richiesto, passa l’**esistente** `dev14c_inference.json` e il PDF `PV8_SLD.pdf` corrispondente (oppure file di altro impianto con proprio baseline dev14c).
5. A «Campione pagine», puoi rispondere `1,2,4` per prova rapida, oppure premere Invio per esaminare tutte le pagine con rimandi reciproci. L’analisi completa può impiegare tempo su PDF con molta grafica.
6. Risultati in `reports\reference_landings.json` e `.csv`. Nel pacchetto è presente anche il campione reale `reports/PV8_reference_landings_sample.json`.

## Interpretazione conservativa

- `REFERENCE_VECTOR_STROKE_CANDIDATE`: un unico tratto verticale solido vicino a un rimando ruotato, ma **non** è una conferma del terminale.
- `AMBIGUOUS_VECTOR_STROKE` o `NO_REFERENCE_VECTOR_STROKE`: nessuna selezione forzata.
- `adjacent_mv_line_cell_text_cue`: testo CELDA/LINEA vicino al tratto, un indizio indipendente dalla posizione, **non** una prova di contatto fisico o continuità.
- Per le altre rotazioni e per disegni non riconducibili a segmenti verticali: diagnosi irrisolta. Questa versione non deve essere considerata generalizzata a tutti gli SLD.

**Obiettivo successivo, non ancora implementato:** identificare gli ingressi/uscite reali delle celle e i dispositivi interposti (interruttori, sezionatori, protezioni) con verifica di continuità per singolo arco del grafo; solo dopo verificare una membership feeder–CU.
