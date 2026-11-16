# SLD2Hierarchy beta3 — Alpha 8: geometria prima dei tag

## Perché esiste

Con Alpha 7, una pagina senza testo nativo (come quelle grafiche di PV2) non
poteva attivare la ricerca dei simboli perché la selezione dei ROI dipendeva
da un tag. Alpha 8 aggiunge una **seconda via indipendente**, mantenendo quella
esistente: ricerca direttamente nei path vettoriali di una pagina, anche senza
OCR o tag. **Le ipotesi trovate non sono asset né terminali accertati.**

## Comando per Windows PowerShell

1. Estrarre l'archivio in una cartella nuova, senza sovrascrivere Alpha 7.
2. Aprire PowerShell nella cartella Alpha 8 ed eseguire
   ` .\run_tests.bat ` e, successivamente, ` .\diagnostica_geometria_senza_tag_PDF.bat `.
3. Inserire il percorso **completo con `.pdf`** (esempio:
   `...\data\CASE_002_PV2\input\PV2_SLD.pdf`) e plant ID `PV2`.
4. Alla richiesta del numero di pagine della scansione geometrica inserire `4`
   per PV2 SLD da quattro pagine. Se il documento reale ha un numero differente,
   il riepilogo mostra le pagine effettive del file.

Output: `reports\alpha8_geometry_first.json` e `.csv`. Per leggere il risultato
basta la console: NON è necessario scaricare o inviare report senza un errore.

La diagnostica Alpha7 `diagnostica_simboli_terminali_PDF.bat` resta disponibile,
ma non è il comando nuovo di Alpha 8. Il workflow integrato supporta anche
`--geometry-first-pages N` (parametro opzionale, disabilitato per impostazione
predefinita per evitare scansioni onerose non richieste).

## Evidenze e limitazioni

* `POLYGON_LINES`: percorso chiuso formato da 20–96 segmenti, dimensioni quasi
  circolari e distanze radiali uniformi. Il progetto reale PV2 contiene anelli
  da 36 segmenti lineari che Alpha 7 non riconosceva.
* `BEZIER_ARCS`: percorso di quattro curve, usato anche in altri disegni.
* Vengono proposti soltanto **gruppi di due o tre cerchi vicini con dimensioni
  coerenti**, con pagine, bbox e identificativi dei path sorgente. Un cerchio
  isolato non basta. Non vengono convertiti in trasformatori per presunzione.
* L'associazione di tag/OCR ai gruppi e la verifica dei terminali sono fasi
  **ancora da implementare/validare**. Un gruppo può essere decorativo o un
  simbolo diverso: solo l'ispezione del disegno può confermarlo.
* Lo stesso PDF può essere esaminato attraverso due strade, ma l'output evita
  di sommarne i candidati come asset fisici. Precision e recall sui veri
  dispositivi rimangono **non misurati** senza benchmark indipendente.
* La scansione percorre i path sorgente dell'intera pagina scelta, ma i gruppi
  riportati sono limitati a 30 per pagina. Gli eventuali gruppi omessi sono
  contati separatamente. Il cap di sicurezza per pagina è 400.000 path; il suo
  superamento viene dichiarato come **non esaminato**, mai come successo.
* `geometry_first_source_scans_complete` significa **soltanto** che i path
  della pagina sono stati sottoposti al filtro preliminare di forme; non prova
  che ogni tipo di simbolo esistente sia supportato o individuato.
* `graph_verified_memberships`, `physical_assets_verified` e
  `physical_terminals_verified` restano 0 nella nuova diagnostica: nessun
  attraversamento di dispositivo è inventato.

## Riscontro sui PDF disponibili in sviluppo

* `PV2.pdf` del corpus: 5 pagine, 4 prive di testo nativo; Alpha 8 ha letto
  geometricamente le quattro pagine e proposto 8 gruppi di tre cerchi (due
  per pagina). Nella pagina 2 il disegno mostra chiaramente gruppi presso
  T1.1/T2.1. **Non equivale a otto asset identificati.**
* Il `PV2_SLD.pdf` locale dell'utente, con quattro pagine, è distinto dal
  `PV2.pdf` completo nel corpus; l'esito va verificato su quel file.
* PV3 può presentare altre forme circolari senza testo: sono ipotesi da
  revisionare, non vengono automaticamente etichettate.
* La logica Alpha7/Alpha6 e il modulo `sld_ci_v04_beta2_dev14c` rimangono
  inalterati salvo la correzione testuale di copertura in `symbol_review_cli`.

## Obiettivo successivo

Associazione conservativa dei gruppi a una simbologia IEC/locale, verifica
indipendente su campioni annotati e recupero dei terminali con tracciabilità
completa (nessuna connessione per sola vicinanza o presenza di rimandi).


## Correzione TEST_FIX (16 ottobre 2026)

Nel caso in cui lo ZIP venga estratto o sincronizzato senza i piccoli PDF di
prova in `sld_ci_v04_beta3/tests/fixtures/`, i test `test_path_trace.py`
falliscono con `FileNotFoundError`. Nello ZIP i file sono presenti, ma la loro
presenza nella cartella effettivamente estratta non e' garantita.

Il comando `run_tests.bat` ora avvia `prepara_fixture_test.py`: controlla gli
11 PDF, ricrea soltanto gli assenti o invalidi con il generatore locale
`fixture_builder.py` e verifica che siano leggibili prima dei 182 test.
Non apre ne' modifica alcun SLD reale; dev14c resta invariato.

Se i PDF non possono essere rigenerati (per esempio per permessi), il comando
esce con un errore esplicito senza dichiarare i test superati.
