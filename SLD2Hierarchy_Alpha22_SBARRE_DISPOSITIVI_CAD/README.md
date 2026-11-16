# SLD2Hierarchy

Ricava da uno **schema unifilare (SLD) in PDF** di un impianto fotovoltaico a
**inverter centralizzati** la gerarchia di asset per SAP:

```
CU (Conversion Unit) → TR (trasformatore) → INV (inverter) → STR_Box (String Box)
```

L'output (CSV `CU;TR;INV;STR_Box` + Excel di stereotipi) è di **staging**: non è
un tracciato di import Matrix FLOW certificato. Ogni relazione è marcata come
candidata, confermata dall'operatore o non risolta; il programma si astiene
piuttosto che inventare asset o collegamenti.

Versione: **0.24.0 (Alpha 22)** — vedi [CHANGELOG.md](CHANGELOG.md).
Stato reale e limiti: [docs/STATO_PRODOTTO.md](docs/STATO_PRODOTTO.md).

## Installazione

Python 3.11+ (verificato con 3.13). Dalla cartella del progetto:

```powershell
python -m pip install -r requirements-lock.txt
```

`requirements-lock.txt` contiene le versioni esatte con cui la suite passa;
`requirements_beta3.txt` solo i vincoli minimi.

Per l'OCR delle etichette QPS nei CAD vettoriali serve inoltre
**Tesseract OCR** installato localmente. Nessuna API esterna viene usata.

## Uso

| Cosa | Come |
|---|---|
| **Analisi di un PDF (uso normale)** | `AVVIA_SLD2HIERARCHY.bat` — GUI con selettore file; sceglie da sola il motore adatto al PDF |
| Esecuzione dei test | `run_tests.bat` (attesi 418: 369 beta3 + 49 dev14c) |
| CAD vettoriale da riga di comando | `strumenti\ANALIZZA_CAD_VETTORIALE.bat` |
| Altre diagnostiche, HITL, integrazione SLD+layout | `strumenti\*.bat` |
| Gerarchia normalizzata per esecuzioni già fatte | `python -m sld_ci_v04_beta3.normalizza_cli --tutte reports` |
| Workbench e CLI di versioni precedenti | `legacy\*.bat` (non più mantenuti) |

Gli output vanno in `reports\…` (una nuova cartella per esecuzione, mai
sovrascritta). Il PDF sorgente è aperto in sola lettura.

Oltre ai file propri del motore, ogni esecuzione dal workbench scrive
`gerarchia_normalizzata.csv`/`.json`: stesso formato per tutti i motori, con
stato del parent e della quantità String Box ricondotto a
`observed / inferred / operator_confirmed / unresolved` (il codice originale
del motore resta in colonna). `unresolved` non significa zero o assente.

### Scelta automatica del motore

| Contenuto del PDF | Motore |
|---|---|
| JSON di review Alpha13 fornito | etichette native (Alpha 12, pipeline dev14c) |
| Tag `XX-TR-n-n` e `XX-INV-n-n` | tag indicizzati (Alpha 15) |
| Etichette `LVL-SB…-INV…` | famiglia LVL (Alpha 16) |
| Nessun testo nativo (solo vettoriale) | CAD vettoriale (Alpha 17–22) |
| Altrimenti | etichette native (Alpha 12) |

### Aggiungere uno stile di SLD

I motori sono plugin in `sld_ci_v04_beta3/engines/`: una sottoclasse di
`Recognizer` dichiara come riconoscere lo stile (`matches`), quale CLI
eseguire e quali file di output leggere. Va poi aggiunta a `ENGINES` in
`engines/registry.py`, prima del motore di ripiego. Il workbench la usa senza
altre modifiche.

### Soglie del motore CAD

Le tolleranze geometriche e i colori dei simboli usati dal motore CAD sono in
[config/soglie_cad_default.json](config/soglie_cad_default.json). Per un nuovo
stile copiare il file, modificarlo e passarlo con `--soglie` alla CLI
`alpha22_cli`. Le soglie effettive sono registrate nel report di audit.

### Attraversamento degli apparecchi (CAD vettoriali)

Un apparecchio in serie trovato in una discontinuità (TR→sbarra,
sbarra→inverter) diventa un **arco-dispositivo** del grafo solo se tratti
realmente disegnati nel PDF coprono, senza lacune oltre
`device_attach_tolerance`, lo spazio fra il capo del conduttore e il simbolo
da entrambi i lati. Quando tutti gli archi esistono, l'audit riporta il percorso
TR → apparecchio → sbarra → apparecchio → inverter come relazione `inferred`:
tipo e stato (aperto/chiuso) degli apparecchi non sono classificati, quindi
non è una continuità elettrica verificata.

Con una review operatore applicata, `alpha22_confronto_review_percorsi.csv`
indica per ogni inverter se la conferma è `SUPPORTATA_DA_PERCORSO`,
`SENZA_PERCORSO_AUTOMATICO` o `IN_CONFLITTO_CON_PERCORSO` (da ricontrollare).

### Review operatore (CAD vettoriali)

Per promuovere CU/TR/INV su un CAD senza testo serve un JSON di review
vincolato a `plant_id` e **SHA256 del PDF** — esempio:
[examples/SETTIMO_TOP_SCHEMA_CONFERMATO_OPERATORE.json](examples/SETTIMO_TOP_SCHEMA_CONFERMATO_OPERATORE.json).
Non applicarlo a PDF diversi da quello per cui è stato scritto.

## Struttura

```
AVVIA_SLD2HIERARCHY.bat     punto d'ingresso
run_tests.bat               test
strumenti/                  launcher di diagnostica / HITL / integrazione
legacy/                     launcher di versioni superate
config/                     profili di soglie
docs/                       stato prodotto, roadmap, requisiti PoC, storico LEGGIMI
examples/                   output di riferimento e review di esempio
sld_ci_v04_beta3/           codice attivo (engines/, sap/, geometry/, integration/, CLI, GUI)
sld_ci_v04_beta2_dev14c/    motore legacy CONGELATO: non modificare
```

## Sviluppo

```powershell
python -m unittest discover -s sld_ci_v04_beta3/tests -t .
python -m unittest discover -s sld_ci_v04_beta2_dev14c/tests
```

Un test (`test_alpha14_workbench`) viene saltato se manca il PDF PV11, che non
è incluso nel repository.

Regole del progetto (da [docs/REQUISITI_POC_SAP.md](docs/REQUISITI_POC_SAP.md)):
nessun ground truth nell'inferenza; nessun asset creato per soddisfare minimi
attesi; `sld_ci_v04_beta2_dev14c` resta congelato; ogni rilascio deve superare
tutti i test vecchi e nuovi. I test misurano la regressione del software, non
l'accuratezza sul mondo reale.
