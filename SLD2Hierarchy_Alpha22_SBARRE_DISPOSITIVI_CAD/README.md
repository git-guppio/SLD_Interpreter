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

Versione: **0.22.1 (Alpha 22)** — vedi [CHANGELOG.md](CHANGELOG.md).
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
| Esecuzione dei test | `run_tests.bat` (attesi 384: 335 beta3 + 49 dev14c) |
| CAD vettoriale da riga di comando | `strumenti\ANALIZZA_CAD_VETTORIALE.bat` |
| Altre diagnostiche, HITL, integrazione SLD+layout | `strumenti\*.bat` |
| Workbench e CLI di versioni precedenti | `legacy\*.bat` (non più mantenuti) |

Gli output vanno in `reports\…` (una nuova cartella per esecuzione, mai
sovrascritta). Il PDF sorgente è aperto in sola lettura.

### Scelta automatica del motore

| Contenuto del PDF | Motore |
|---|---|
| JSON di review Alpha13 fornito | etichette native (Alpha 12, pipeline dev14c) |
| Tag `XX-TR-n-n` e `XX-INV-n-n` | tag indicizzati (Alpha 15) |
| Etichette `LVL-SB…-INV…` | famiglia LVL (Alpha 16) |
| Nessun testo nativo (solo vettoriale) | CAD vettoriale (Alpha 17–22) |
| Altrimenti | etichette native (Alpha 12) |

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
docs/                       stato prodotto, roadmap, requisiti PoC, storico LEGGIMI
examples/                   output di riferimento e review di esempio
sld_ci_v04_beta3/           codice attivo (sap/, geometry/, integration/, CLI, GUI)
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
