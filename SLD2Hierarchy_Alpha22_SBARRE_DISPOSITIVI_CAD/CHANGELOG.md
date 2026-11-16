# Changelog

Le note di rilascio originali, complete, sono in [docs/storico/](docs/storico/)
(`LEGGIMI_ALPHAn.md`).

## 0.24.0 — archi-dispositivo nei CAD vettoriali (2026-11-16)

- Nuovo stadio `sap/cad_device_edges.py`: un apparecchio in serie viene
  attraversato come arco tipizzato `DEVICE` solo se tratti disegnati (qualsiasi
  colore, non tratteggiati) coprono i due spazi residui capo→simbolo→capo lungo
  l'asse del ramo. Lacune oltre `device_attach_tolerance` lasciano il gap aperto.
- Percorsi TR → apparecchio → sbarra → apparecchio → inverter riportati
  nell'audit come relazione `inferred` (`PATH_THROUGH_UNCLASSIFIED_DEVICES`);
  tipo/stato degli apparecchi non classificati, continuità verificata sempre 0.
- CSV Alpha22 aggiornati: `discontinuita_protezione` =
  `ATTRAVERSATE_CON_ARCHI_DISPOSITIVO` e `arco_dispositivo_creato` = `SI` dove
  l'arco esiste; altrimenti valori invariati.
- Confronto review operatore / percorsi disegnati
  (`alpha22_confronto_review_percorsi.csv`); la review non viene modificata.
- **Fix:** sulle pagine con lato < 1000 pt (A4/A3) la ricerca dei simboli in serie
  e l'anteprima PNG usavano una scala diversa da quella dei conduttori; ora
  tutti gli stadi usano `frame_scale`. Nessun effetto su pagine grandi come Settimo.
- Nuove soglie `device_axis_tolerance`, `device_attach_tolerance`.
- 14 nuovi test (418 in totale), incluso un PDF sintetico con topologia tipo Settimo.
- **Non validato su PDF reali**: i PDF di impianto non sono nel repository.

## 0.23.0 — motori come plugin, modello dati unico, soglie configurabili (2026-11-16)

- Nuovo pacchetto `engines/`: ogni motore (etichette native, tag indicizzati,
  LVL, CAD vettoriale) è un `Recognizer` con regola di riconoscimento, comando
  e lettura degli output. Il workbench sceglie il motore dal registro invece
  che da `if` cablati; gli identificativi storici (`alpha12`, `alpha15-indexed`,
  `alpha16-lvl`, `alpha21-cad`) restano invariati.
- Modello dati unico (`engines/model.py`): i due formati di CSV di evidenze dei
  motori vengono letti in un'unica struttura con stati
  `observed / inferred / operator_confirmed / unresolved`. Codici sconosciuti
  diventano `unresolved` (mai "confermato").
- Ogni esecuzione dal workbench scrive `gerarchia_normalizzata.csv`/`.json`;
  `normalizza_cli` fa lo stesso per esecuzioni già esistenti.
- Soglie del motore CAD Alpha22 (sbarra, avvolgimento, colori dei simboli in
  serie) estratte in `CadBusThresholds`, profilo `config/soglie_cad_default.json`,
  opzione `--soglie`. Default identici al comportamento precedente; soglie
  registrate nel report di audit; profilo non valido = errore prima di scrivere output.
- 20 nuovi test (404 in totale).

## 0.22.1 — consolidamento (2026-11-16)

- **Fix:** crash della pipeline CAD vettoriale (Alpha 18→22) con OpenCV 5:
  `HoughLinesP` restituisce ora un array N×4 invece di N×1×4. Gestite entrambe le forme.
  La suite torna a 384/384 (335 beta3 + 49 dev14c, 1 skip per PDF PV11 assente).
- Aggiunti i `__init__.py` mancanti in `sld_ci_v04_beta3` e sottopacchetti e il
  `__main__.py` (`python -m sld_ci_v04_beta3` documentato nel README ora funziona).
- Aggiunto `requirements-lock.txt` con le versioni verificate.
- Versione unica in `sld_ci_v04_beta3.__version__`, mostrata nel titolo della GUI
  (prima indicava "Alpha 21").
- Launcher riorganizzati: in radice solo `AVVIA_SLD2HIERARCHY.bat` e `run_tests.bat`;
  diagnostiche in `strumenti/`, versioni superate in `legacy/`.
  Nuovo `strumenti/ANALIZZA_CAD_VETTORIALE.bat` (CLI Alpha 22).
- Messaggio "Tkinter non disponibile" ora indica un'alternativa che non richiede Tkinter.
- Documentazione: nuovo `README.md`; LEGGIMI storici in `docs/storico/`;
  stato, roadmap e requisiti in `docs/`.

## Storico Alpha

| Versione | Contenuto |
|---|---|
| Alpha 22 | Sbarre CAD e discontinuità documentate; motivi di apparecchiatura in serie candidati |
| Alpha 21 | QPS CAD = String Box; struttura CU/TR/INV confermata dall'operatore (vincolo SHA256 PDF) |
| Alpha 20 | Tracciamento dei conduttori CAD fino ai morsetti; OCR QPS locale |
| Alpha 19 | Ipotesi grafiche ordinali controllabili; roadmap verso la versione operativa |
| Alpha 18 | Candidati inverter strutturali nei CAD vettoriali (colore/forma) |
| Alpha 17 | Diagnostica dei CAD vettoriali senza testo |
| Alpha 16 | Terza famiglia documentale: etichette LVL-SB (PV8) |
| Alpha 15 | Riconoscimento multistile, tag indicizzati (PV5/6/7) |
| Alpha 14 | Workbench unico punto di accesso |
| Alpha 13 | Verifica visiva delle evidenze PDF (HITL per inverter) |
| Alpha 12 | Gerarchie stereotipate, export CSV + Excel; selezione file da GUI |
| Alpha 11 | Parentage TR/INV con conferme HITL |
| Alpha 10 | Diagnostica documentale SAP-first da etichette |
| Alpha 9 | SAP-first, staging Matrix FLOW; requisiti PoC congelati |
| Alpha 8 | Geometria prima dei tag |
| Alpha 7 | Simboli e contatti candidati; triage multistile |
| Alpha 6 | Diagnostica affidabile, benchmark corpus |
| Alpha 5 | Triage multistile, integrazione SLD + layout |
| Alpha 4 | Diagnostica approdi dei rimandi |
| Alpha 3 | Rimandi tra pagine |
| Alpha 2 | Prima integrazione beta3 |
