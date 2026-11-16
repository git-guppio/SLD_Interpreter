# Analisi tecnica — SLD2Hierarchy Alpha 22 (SBARRE / DISPOSITIVI CAD)

**Cartella analizzata:** `SLD2Hierarchy_Alpha22_SBARRE_DISPOSITIVI_CAD/`
**Data analisi:** 16/11/2026
**Metodo:** lettura del codice sorgente, dei launcher `.bat` e della documentazione interna (`LEGGIMI_*`, `STATO_PRODOTTO_*`, `ROADMAP_*`, `ALPHA9_REQUISITI_POC_SAP.md`). La suite di test **non è stata eseguita** in questo ambiente perché PyMuPDF non è installato: i "384/384 test superati" citati nella documentazione non sono stati verificati qui.

---

## 1. In sintesi

SLD2Hierarchy è un prototipo Python (circa 20.000 righe di codice, più test) che legge uno **schema unifilare (SLD) in PDF** di un impianto fotovoltaico a **inverter centralizzati** e ne ricava una gerarchia di asset per SAP:

```
CU (Conversion Unit) → TR (trasformatore) → INV (inverter) → STR_Box (String Box)
```

L'output è un CSV `CU;TR;INV;STR_Box` e un Excel di "stereotipi" di **staging**, destinati in futuro a Matrix FLOW. Non è un tracciato di import certificato.

Il progetto ha una filosofia molto chiara e coerente: **astenersi piuttosto che inventare**. Ogni relazione è marcata come *candidata*, *confermata dall'operatore* o *non risolta*, e non si attraversano mai interruttori o discontinuità per supposizione.

I limiti principali sono l'accumulo di versioni (Alpha 2 → 22) senza consolidamento, regole euristiche legate a specifici stili grafici, l'assenza di una vera misura di accuratezza e una struttura del codice poco manutenibile.

---

## 2. Funzionamento

### 2.1 Architettura

| Componente | Ruolo | Stato |
|---|---|---|
| `sld_ci_v04_beta2_dev14c/` | Motore "legacy": estrazione testo/simboli, OCR, line tracing, riconciliazione SLD+layout, GUI operatore per i feeder MT | **Congelato** (non modificabile per contratto) |
| `sld_ci_v04_beta3/geometry/` | Kernel di connettività vettoriale (segmenti, giunzioni, tratteggi, indice spaziale) | Ricerca |
| `sld_ci_v04_beta3/integration/` | Integrazione SLD+layout, rimandi tra fogli, multistile, ponte semantico | Alpha 5–8 |
| `sld_ci_v04_beta3/sap/` | Moduli SAP-first, uno per release (`*_alpha11` … `*_alpha22`) | Attivo |
| `sld_ci_v04_beta3/*_cli.py` | Una CLI per ogni release (`alpha15_cli` … `alpha22_cli`, `sap_cli`, …) | Attivo |
| `sap_workbench_alpha16.py` | GUI Tkinter unificata (punto d'ingresso attuale) | Attivo |
| `*.bat` (circa 30) | Launcher Windows per ogni funzione o versione | Misti, molti obsoleti |
| `examples/` | Output di riferimento e JSON di review operatore | Dati |

### 2.2 Punto d'ingresso e dispatch automatico

`AVVIA_SLD2HIERARCHY.bat` → `python -m sld_ci_v04_beta3.sap_workbench_alpha16`

La GUI chiede il PDF, l'ID impianto e un eventuale JSON di review. Poi `choose_recognition_mode()` sceglie il motore guardando le prime 3 pagine:

| Condizione rilevata nel PDF | Modalità | CLI lanciata |
|---|---|---|
| Esiste un JSON di review Alpha13 | `alpha12` | `sap_cli` (pipeline dev14c + export SAP) |
| Tag testuali `XX-TR-n-n` **e** `XX-INV-n-n` | `alpha15-indexed` | `alpha15_cli` |
| Etichette `LVL-SB.x.y.z-INV.a.b` | `alpha16-lvl` | `alpha16_cli` |
| PDF solo vettoriale, senza testo nativo | `alpha21-cad` | **`alpha22_cli`** |
| Altrimenti | `alpha12` | `sap_cli` |

L'elaborazione gira in un sottoprocesso (`subprocess.Popen`) su un thread separato. Ogni esecuzione scrive in una nuova cartella `reports/sap_alpha16/<impianto>/<timestamp>`, quindi non sovrascrive mai i risultati precedenti.

### 2.3 Famiglie di riconoscimento

1. **Etichette native (Alpha 10–12, stile PV11 Pampa Norte).** `label_first.py` cerca sequenze di parole come `C 12`, `I 3.2`, `TRANSFORMER 1.700`, `10 STRING BOX` e assegna i parent con finestre di località in pixel. `stereotypes_alpha12.py` produce CSV e XLSX; l'XLSX è scritto a mano via `zipfile` + XML, senza openpyxl.
2. **Tag indicizzati (Alpha 15, PV5/6/7).** Regex `XX-TPO|TR-n-n`, `XX-INV-n-n`, `XX-CST|CBX|SCB-…`, `CENTRO DE TRANSFORMACIÓN CT-n`.
3. **Famiglia LVL (Alpha 16, PV8).** Regex `Inv.n.n`, `LVL-SB…`, `Subcampo n.`
4. **CAD solo vettoriale (Alpha 17–22, Settimo/PV3).** È la pipeline di questa release:
   - **Alpha 17–18:** il PDF viene rasterizzato e i candidati si cercano per **colore** (pannelli ciano = inverter, pettine rosso = bus d'uscita, glifo diagonale).
   - **Alpha 19:** correlazione ordinale tra inverter grafici e campi a valle.
   - **Alpha 20:** estrazione dei segmenti neri continui dal vettoriale PDF, tracciamento dei conduttori d'ingresso fino al morsetto aperto, rilevamento di coppie di cerchi (avvolgimenti TR) e quadri DC. OCR Tesseract locale delle etichette `QPS-n-k/N`.
   - **Alpha 21:** sequenze QPS complete → String Box per inverter. CU, TR e INV vengono promossi **solo** con un JSON di review operatore vincolato a schema, `plant_id` e **SHA256 del PDF**.
   - **Alpha 22** (`cad_bus_provenance_alpha22.py`):
     - `identify_common_buses`: cerca un **unico segmento nero orizzontale** che copra tutti i morsetti degli inverter (servono almeno 2 ingressi). Se due sbarre parallele sono equivalenti, si astiene.
     - `match_winding_to_bus`: cerca una coppia di avvolgimenti **più** un tratto verticale sorgente che scenda verso la sbarra.
     - `detect_series_apparatus_motifs`: cerca nei gap non attraversati i simboli verdi/magenta (possibili apparecchi in serie), senza classificarli.
     - Output: audit JSON, CSV delle relazioni candidate, CSV dei dispositivi in serie, PNG panoramica e zoom.

### 2.4 Flusso Alpha 22 (`alpha22_cli.main`)

```
PDF ──► inspect_cad_conductor_runs (Alpha18→19→20 + OCR)
     ──► build_alpha21_hierarchy (+ eventuale review operatore validata)
     ──► audit_cad_pdf (sbarra, avvolgimento, motivi in serie)
     ──► scrittura output (solo dopo che la validazione è passata)
```

### 2.5 Garanzie di progetto (punti di forza)

- **Il ground truth non entra mai nell'inferenza.** I TXT e gli inventari servono solo per il confronto.
- **Review vincolate alla fonte:** schema, `plant_id`, SHA256 del PDF e del report, numero di conferme coerente con le verifiche visive.
- **Astensione esplicita** con codici di stato leggibili (`AMBIGUOUS_PARALLEL_BUSBARS`, `ABSTAIN_INCOMPLETE_SOURCE`, …).
- **Tracciabilità:** indici dei segmenti e dei path sorgente, bbox, immagini di evidenza per l'HITL.
- **Nessuna rete:** tutto è locale, incluso l'OCR.
- **Documentazione onesta sui limiti:** "384/384 è regressione software, non precisione sul mondo reale".

---

## 3. Criticità

### 3.1 Struttura e manutenibilità (priorità alta)

| # | Criticità | Evidenza |
|---|---|---|
| C1 | **Versioni accumulate invece che consolidate.** Ogni Alpha aggiunge un modulo, una CLI, un `.bat` e un LEGGIMI, senza rimuovere i precedenti. | 3 workbench (`alpha14/15/16`), 10+ CLI `alphaNN_cli.py`, circa 30 `.bat`, 22 `LEGGIMI_ALPHA*.md` |
| C2 | **Nomi incoerenti con la versione.** `AVVIA_SLD2HIERARCHY.bat` dice "ALPHA 22", la finestra GUI dice "Alpha 21", il modulo si chiama `sap_workbench_alpha16`, la docstring dice "Alpha17" e la modalità CAD si chiama `alpha21-cad` ma lancia `alpha22_cli`. | `sap_workbench_alpha16.py` |
| C3 | **Pacchetto Python incompleto.** Mancano `__init__.py` in `sld_ci_v04_beta3/`, `geometry/`, `integration/`, `tests/` e in tutto `sld_ci_v04_beta2_dev14c/` (c'è solo `sap/__init__.py`). Funziona come *namespace package*, ma `unittest discover -t .` fallisce ("Start directory is not importable"). Inoltre `python -m sld_ci_v04_beta3`, documentato nel README, non funziona perché manca `__main__.py`. È probabile che i file vuoti siano andati persi in zip o sync OneDrive. | verificato con `find` e `unittest` |
| C4 | **Stile di codice compresso.** Più istruzioni per riga separate da `;`, variabili di una lettera (`p`, `a`, `h`), funzioni annidate e nessuna type hint nei moduli recenti. Questo rende difficile la code review. | `alpha22_cli.py`, `cad_bus_provenance_alpha22.py` |
| C5 | **Logica duplicata in `portfolio_rows`.** Cinque blocchi quasi identici, uno per schema, con lettura JSON ripetuta e un intero blocco Alpha21 copiato due volte. Le variabili `qps_count` vengono calcolate ma non usate. | `sap_workbench_alpha16.py`, righe ~100–260 |
| C6 | **Nessuna gestione dipendenze o packaging.** C'è solo `requirements_beta3.txt` con versioni minime: niente lock, `pyproject` o ambiente virtuale. Tesseract è un prerequisito esterno non verificato all'avvio. | `requirements_beta3.txt` |
| C7 | **Nessun versioning git.** La cartella non è un repository; le versioni sono distinte solo dal nome della cartella o dello zip. | ambiente |

### 3.2 Generalizzazione dell'algoritmo (priorità alta)

| # | Criticità | Evidenza |
|---|---|---|
| G1 | **Regole cablate su uno stile specifico.** `label_first` riconosce un TR solo se il testo è `TRANSFORMER` seguito da `1.700`, cioè la potenza di PV11. Un TR da 2.500 kVA non viene trovato. | `label_first.py:49` |
| G2 | **Riconoscimento CAD basato su colori esatti.** Gli inverter sono pannelli **ciano**, il bus è **rosso**, i dispositivi in serie sono path con colore **esattamente** `(0,1,0)` o `(1,0,1)`. Un CAD con palette diversa, o esportato in scala di grigi, non produce nulla. | `vector_semantics_alpha18.py`, `cad_bus_provenance_alpha22.py` |
| G3 | **Soglie geometriche "magiche".** Ad esempio `max_gap=19.0`, `transverse_tolerance=2.8`, la finestra `-20≤dx≤270, 95≤dy≤255` di `_nearest_cu` e il rapporto d'aspetto `.65–1.45`. Sono espresse in pixel di un rendering normalizzato a 1000 px e tarate su pochi PDF. | vari moduli |
| G4 | **Sbarra solo orizzontale, solo pagina 1 per l'OCR.** Una sbarra verticale o spezzata in più segmenti collineari non viene riconosciuta. L'OCR QPS considera solo la pagina 1 (`k=(1, …)`). | `identify_common_buses`, `verified_qps_sequences` |
| G5 | **Giunzioni a T non collegate per scelta.** È una scelta conservativa e voluta, ma su CAD reali produce molti falsi negativi. | `_neighbor_pairs` |
| G6 | **Corpus di validazione molto ridotto e non indipendente.** Settimo e PV3 sono quasi duplicati; PV11, PV6 e PV8 sono stati usati anche per sviluppare le regole. | `STATO_PRODOTTO_ALPHA22.md` |

### 3.3 Funzionalità ancora aperte (bloccanti per il prodotto)

- **0 collegamenti TR→INV automatici completi su Settimo.** La parentela dipende interamente dalla conferma dell'operatore.
- Gli apparecchi di manovra e protezione **non vengono attraversati né classificati**; la classificazione di IOCB e TR LV/LV non è implementata.
- **Nessun contratto Matrix FLOW:** il CSV è solo di staging.
- **Nessuna metrica** di precision, recall o accuratezza parent su dati held-out.

### 3.4 Robustezza ed esperienza d'uso

| # | Criticità |
|---|---|
| R1 | Il PDF viene aperto e renderizzato più volte nella pipeline CAD (Alpha18, 19, 20, 22, OCR), con costi alti sui PDF multipagina. Il README beta3 dichiara anche una complessità O(n²) del kernel geometrico. |
| R2 | Il JSON di review operatore va scritto a mano: serve calcolare lo SHA256 del PDF e rispettare lo schema. Non c'è un editor guidato in GUI. |
| R3 | Molti `.bat` usano `set /p` per i percorsi: sono fragili con virgolette, `&` e caratteri accentati. |
| R4 | Ci sono 15 `except Exception`/`except:` (soprattutto nel codice dev14c e in `integrated_case.py`) che possono nascondere errori reali. `portfolio_rows` scarta in silenzio i report malformati. |
| R5 | I messaggi della GUI sono lunghi e tecnici: le cautele, utili, rendono l'output poco leggibile per un operatore non sviluppatore. |
| R6 | Nessun log strutturato su file: l'output del sottoprocesso finisce solo nella text box della GUI. |

---

## 4. Miglioramenti attuabili

### 4.1 Interventi rapidi (giorni)

1. **Ripristinare i `__init__.py`** mancanti e aggiungere `sld_ci_v04_beta3/__main__.py`. Poi verificare `run_tests.bat` su una macchina pulita, come primo controllo di integrità del pacchetto.
2. **Allineare nomi e versioni:** rinominare il workbench in `workbench.py`, aggiornare il titolo GUI, rinominare la modalità `alpha21-cad` in `cad-vector` e introdurre una costante `__version__` unica.
3. **Fare pulizia dei launcher:** tenere solo `AVVIA_SLD2HIERARCHY.bat`, `run_tests.bat` e un `diagnostica.bat`, spostando gli altri in `legacy/`.
4. **Unificare la documentazione:** un solo `README.md` (installazione, uso, output, limiti) e un `CHANGELOG.md` al posto dei 22 LEGGIMI.
5. **Rendere parametrico `label_first`:** sostituire `nxt == '1.700'` con una regex di potenza (`\d[\d.,]*\s*kVA`).
6. **Fare un controllo prerequisiti all'avvio** (PyMuPDF, Pillow, numpy, Tesseract) con un messaggio chiaro in GUI.

### 4.2 Interventi strutturali (settimane)

1. **Architettura a plugin per gli stili.** Definire un'interfaccia comune, per esempio `Recognizer.detect(pdf) -> score` e `Recognizer.extract(pdf) -> Hierarchy`, implementata da LabelFirst, Indexed, LVL e CadVector. Il dispatcher sceglie per punteggio, e aggiungere uno stile non richiede più una nuova Alpha completa.
2. **Modello dati unico.** Definire dataclass o pydantic per `Asset`, `Relation(status=observed|inferred|operator_confirmed|unresolved)` ed `Evidence(source_ids, bbox, page)`, sostituendo i dict con chiavi stringa sparse fra i moduli.
3. **Configurazione esterna delle soglie.** Spostare le tolleranze in un file YAML per profilo di stile, con valori espressi in unità relative alla pagina o allo spessore linea invece che in pixel assoluti.
4. **Colori come parametro, non come regola.** Classificare per clustering di palette o per ruolo (linee spesse = bus) e usare il colore solo come indizio aggiuntivo.
5. **Generalizzare la sbarra:** accettare orientamento verticale, fondere segmenti collineari contigui e gestire più pagine; estendere l'OCR a tutte le pagine pertinenti.
6. **Cache della pipeline:** aprire il PDF una volta sola, estrarre `get_drawings()` e il rendering una volta per pagina e condividerli fra gli stadi. Applicare l'indice spaziale (già presente in `geometry/spatial_index.py`) ovunque si cerchino vicini.
7. **Mettere il progetto sotto git** con CI locale (pre-commit con `ruff`/`black`, test automatici). Lo storico delle Alpha diventa storico dei commit e dei tag.

### 4.3 Evoluzioni funzionali (verso il prodotto)

1. **Attraversamento degli apparecchi come archi tipizzati.** Riconoscere interruttore, sezionatore e TA tramite una libreria di template di simboli (IEC 60617) e inserirli nel grafo come archi `DEVICE(type, state)`. Così TR→INV si chiude automaticamente quando tutti gli archi sono classificati. È il blocco n. 1 indicato in `STATO_PRODOTTO_ALPHA22.md`.
2. **Editor di review in GUI.** L'operatore clicca su sbarra, TR e inverter nell'immagine di evidenza; la GUI genera il JSON di review con SHA256 calcolato automaticamente. Questo elimina gli errori di compilazione manuale (R2).
3. **Benchmark held-out.** Formalizzare il corpus (già previsto da `CORPUS_MANIFEST_DA_COMPILARE.json`) con divisione dev/test, annotazioni per bbox, tipo e parent, e uno script che calcoli precision, recall e accuratezza parent per stile. La metrica deve far parte del rilascio, accanto ai test.
4. **Contratto Matrix FLOW.** Ottenere lo schema di import reale, scrivere un validatore e un exporter dedicati e fare una prova di caricamento end-to-end.
5. **Fallback raster/ML** per i PDF scansionati o con stili non coperti, cioè un detector di simboli addestrato. Va inquadrato come candidato soggetto a HITL, coerentemente con la filosofia di astensione.

---

## 5. Priorità consigliata

| Priorità | Azione | Impatto |
|---|---|---|
| 1 | Ripristino del packaging + esecuzione dei test su ambiente pulito | Integrità e riproducibilità |
| 2 | git + pulizia di launcher, documentazione e nomi | Manutenibilità |
| 3 | Benchmark held-out con metriche | Misura reale del valore |
| 4 | Architettura a plugin + modello dati unico + soglie configurabili | Generalizzazione |
| 5 | Riconoscimento e attraversamento degli apparecchi in serie | Sblocca TR→INV automatico |
| 6 | Editor di review in GUI | Riduce il costo dell'HITL |
| 7 | Contratto e test d'import Matrix FLOW | Messa in produzione |

---

## 6. Conclusione

Il prototipo è **metodologicamente solido**: tracciabilità, astensione, review vincolate allo SHA256 e separazione dal ground truth sono scelte corrette per un dominio in cui un errore di gerarchia SAP costa caro.

Il valore pratico oggi è però limitato a pochi stili di disegno noti. Su CAD senza testo, la gerarchia dipende dalla conferma dell'operatore. La crescita "per Alpha incrementali" ha prodotto debito tecnico che rallenterà ogni passo successivo. Prima di aggiungere nuove capacità conviene **consolidare** (packaging, git, architettura a plugin, modello dati unico) e **misurare** (benchmark held-out), poi affrontare il riconoscimento degli apparecchi in serie, che è il vero blocco funzionale.
