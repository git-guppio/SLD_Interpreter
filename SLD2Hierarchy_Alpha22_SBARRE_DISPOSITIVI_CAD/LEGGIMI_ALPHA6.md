# SLD2Hierarchy — Alpha 6 (diagnostica affidabile e verificabile)

**Obiettivo:** correggere il blocco `DRAWING_COMPLEXITY_SAFETY_CAP` osservato su PV4 e fornire fondamenta misurabili prima di attribuire continuità elettrica. Nessuna modifica a `sld_ci_v04_beta2_dev14c`.

## Come eseguire su Windows

1. Estrarre tutto lo ZIP in una cartella nuova, preservando le sottocartelle.
2. Aprire PowerShell nella cartella estratta, eseguire `./run_tests.bat` oppure `./diagnostica_multistile_PDF.bat` (in PowerShell Windows si può usare anche `.\run_tests.bat` e `.\diagnostica_multistile_PDF.bat`). Non è necessario `cmd /k`.
3. Inserire il percorso completo del PDF, **compreso `.pdf`**, e un ID impianto facoltativo.
4. La diagnostica salva `reports/multistyle_preflight.json` e `.csv` e non cambia documenti sorgenti.
5. Il CSV ha separatore `;`, codifica UTF-8 BOM. Contiene `geometry_status`, `roi_caps` e `short_segments` per ciascuna pagina. Si può leggere dal prompt con `type reports\multistyle_preflight.csv`.

## Cambiamenti rispetto ad Alpha 5

* **Analisi ROI sulle pagine dense:** `get_cdrawings()` estrae i vettori, ma la sicurezza `--max-drawings` si applica **ai disegni che intersecano la singola regione**, non all'intera pagina. Le ROI sono selezionate dai tag nativi. Vengono presi solo i tratti che geometricamente intersecano la ROI. Un eccesso locale diventa `ROI_COMPLEXITY_SAFETY_CAP` e non produce risultati ingannevoli.
* **Indice spaziale del kernel:** `SegmentIndex` usa celle e fallback per segmenti molto lunghi. Riduce i confronti tra coppie di segmenti con riquadri non sovrapposti. Non cambia la politica delle connessioni: incroci senza punto di giunzione, tratti tratteggiati e dispositivi interposti non vengono uniti arbitrariamente.
* **Micro-segmenti e tratteggi:** i tratti brevi nella ROI vengono contati e mantenuti come diagnostica. `find_microdash_candidates()` individua allineamenti ripetuti con intervalli compatibili con tratteggi; **non** li collega, perché potrebbero rappresentare confini grafici.
* **Identità dei tag:** `tag_identity_groups` raccoglie tutte le occorrenze per `(tag_type, tag_normalizzato)` e conserva pagine, coordinate e varianti di scrittura. Sono **candidati per identità**, non asset fisici deduplicati. I tag ripetuti sono segnalati per revisione, non sommati.
* **Conteggi per provenienza:** `count_provenance` tiene separati i tag nativi, i candidati univoci e le grandezze non ancora misurate (`null`, non `0`). Il report integrato `beta3_count_provenance` distingue i conteggi aggregati dev14c, le appartenenze strutturalmente inferite, quelle esplicitamente documentate e quelle verificate dal grafo. La ripartizione completa per singolo asset tra simboli/tabelle/regole **non è ancora disponibile**: non viene inventata.
* **Benchmark del corpus:** comando `python -m sld_ci_v04_beta3.corpus_cli --manifest "manifest.json"`. Esempio `examples/CORPUS_MANIFEST_DA_COMPILARE.json`: sostituire i percorsi. Facoltativo `annotation_file` con JSON contenente `tag_annotations` (lista di `{ "tag_type": "TRANSFORMER_TAG", "tag": "XFR-01" }`), provenienti **esclusivamente da annotazione umana indipendente**. I risultati di precision/recall sono allora **solo per estrazione dei tag**, non per istanze fisiche. Se manca l'annotazione, le metriche sono dichiarate non calcolabili; i benchmark basati su soli conteggi non possono individuare falsi positivi compensati da falsi negativi.

## Limiti e policy di sicurezza

- Un tag non è un asset fisico; un tratto vicino a un tag non è un terminale elettrico; un gruppo documentale non dimostra connettività conduttiva.
- I controlli sull'intero corpus classificano le pagine; **le ROI sono campionate** per budget (predefinito 3 pagine × 3 regioni per la diagnostica, 1 × 1 per il benchmark). Il CSV non è una certificazione di copertura geometrica totale.
- `get_cdrawings()` deve comunque estrarre i tracciati della pagina, e la memoria su PDF CAD estremamente densi resta un fattore da monitorare. Il limite di sicurezza per ROI e il conteggio degli oggetti vengono conservati.
- Nessuna connessione feeder–CU è promossa automaticamente a `GRAPH_VERIFIED`.
- La vera precisione/recall per tipo di **dispositivo fisico** richiede Ground Truth per singola istanza, parent/tag, bbox e matching one-to-one. Questo lavoro non è sostituibile con il confronto di soli totali numerici.

## Test e prove

Unit test: **114 beta3 + 49 dev14c = 163**. Test locali Alpha6: pagine dense (cap per ROI), tratti tratteggiati brevi, crossing, indice spaziale, tag ripetuti con provenienza, conteggi di fonte, dati insufficienti per P/R e caso `TP=1, FP=1, FN=1` con conteggi assoluti coincidenti. Su PV4 originale è stata elaborata una pagina con **285.957 oggetti vettoriali** senza blocco a livello pagina; le ROI mantengono sempre flag di mancata verifica elettrica. Corpus confrontato: 7 PDF PV2–PV8 più 2 PDF GRE/Jaguito (gli ultimi solo come sorgenti documentali, non attribuendo una diagnosi di impianto unificata).
