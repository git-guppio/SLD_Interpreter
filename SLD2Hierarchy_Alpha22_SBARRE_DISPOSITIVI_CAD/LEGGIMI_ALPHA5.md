# SLD2Hierarchy - Integrated Alpha 5: triage multistile

**Obiettivo di questa release:** evitare che l'analisi si arresti quando mancano i rimandi reciproci fra subcampi del tipo PV8. Alpha5 sceglie percorsi *diagnostici* in base alle evidenze presenti su ogni pagina, senza codificare un layout fisso di impianto.

**Non e' ancora un verificatore end-to-end feeder -> CU.** Riconoscere un tag, una matchline, un riferimento a una tavola o un segmento vicino non dimostra terminali elettrici ne' continuita' attraverso un dispositivo.

## Novita' rispetto ad Alpha4

- Pagine con `A / DE SUBCAMPO N`: segnala `CU_CROSS_SHEET_DOCUMENTARY` (preflight); il modulo Alpha3/Alpha4 continua a svolgere il controllo reciproco e degli approdi, invariato.
- Pagine con `MATCHLINE ...`: segnala `MATCHLINE_DOCUMENTARY_UNQUALIFIED`, senza creare archi elettrici. L'eventuale target `E-136A` rimane una citazione di tavola, non un collegamento automatico.
- Pagine con `SEE SHEET`, `VER PLANO`, ecc.: segnala `DRAWING_REFERENCE_ONLY`. I documenti esterni e le note non sono considerati feeder o continuita'.
- Pagine con ID di dispositivi (`NNB-TPO-02-01`, `IBR-CTR-01`, `XFR-38`, inverter, combiner): seleziona fino a tre regioni geometriche per pagina attorno a etichette specifiche e conserva esempi di segmenti con pagina, identificativo, coordinate e provenienza.
- Pagine senza testo PDF nativo: segnala `NO_NATIVE_TEXT_OCR_ELIGIBLE`; **solo su richiesta**, esegue una preview OCR conservativa tramite il comando esterno Tesseract, se disponibile. L'OCR non crea asset automaticamente; in alcuni documenti, come PV3, non ricava alcun indizio affidabile.
- Safety cap sulle pagine con troppi oggetti grafici; invece di forzare l'elaborazione, riporta `DRAWING_COMPLEXITY_SAFETY_CAP`.

## Integrazione con l'elaborazione dev14c esistente

Lanciando `esegui_integrazione.bat`, Alpha5 aggiunge al report principale la
sezione `beta3_multistyle_preflight` e salva il report dettagliato separato
in `reports\integrated_run\multistyle_preflight.json`. La coda delle CU, il
calcolo della gerarchia dev14c, l'analisi dei rimandi reciproci e il resto
del report integrato sono mantenuti. Per evitare di ricalcolare le pagine di
PV8 si puo' riutilizzare un baseline validato come in Alpha2 (nome, impianto
e numero pagine; non identita' byte-per-byte del PDF). L'integrazione di
Alpha5 aggiunge soltanto diagnostica, **non** nuovi collegamenti verificati.

## Comandi Windows

Apri PowerShell **dalla cartella in cui hai estratto Alpha5** ed esegui:

```powershell
cmd /k ".\run_tests.bat"
```

Per la nuova diagnostica usa:

```powershell
cmd /k ".\diagnostica_multistile_PDF.bat"
```

Quando richiesto, inserisci il percorso completo del PDF e l'identificativo dell'impianto. Non e' necessario fornire una precedente inferenza dev14c. A fine esecuzione troverai `reports\multistyle_preflight.json` e `.csv`.

- La risposta predefinita alla richiesta di OCR e' **NO**. Se scegli `s`, deve esserci Tesseract installato e disponibile nel PATH; il codice riporta `DEPENDENCY_UNAVAILABLE` se manca, senza interrompere il resto della diagnostica.
- Per file con migliaia di disegni vettoriali la scansione puo' durare da qualche secondo a oltre 20 secondi.
- Alternativa diretta CLI per prove parziali:

```powershell
python -m sld_ci_v04_beta3.multistyle_cli --pdf "C:\percorso\PV4.pdf" --plant-id PV4 --max-pages 10 --max-probe-pages 2
```

`--max-pages 10` e' una **scansione parziale** che non deve essere descritta come copertura integrale. `--max-probe-pages` limita le pagine scelte per il controllo geometrico: la classificazione testuale copre comunque tutte le pagine richieste.

## Esiti di verifica locale del 15 ottobre 2026

- PV2: 5/5 pagine classificate, 4 senza testo nativo, nessuna area con tag specifici identificati.
- PV3: 1/1 classificata, 1 senza testo nativo; OCR preview eseguita in ambiente di sviluppo senza ricavare token tecnici affidabili.
- PV4: 71/71 classificate, 15 pagine con `MATCHLINE`, 37 con tag di attrezzature, 6 regioni geometriche esaminate. Una pagina oltre il limite di complessita' e' stata esclusa dal controllo geometrico. Le 71 pagine **non** sono state tutte sottoposte a tracciamento del grafo.
- PV5: 14/14 classificate; 9 regioni geometriche su 3 pagine.
- PV6: 4/4 classificate; 9 regioni geometriche su 3 pagine.
- PV7: 3/3 classificate; 9 regioni geometriche su 3 pagine.
- PV8 (PDF integrale con layout + SLD): 56/56 classificate; presenti rimandi `SUBCAMPO` in 55 pagine, geometria non ripetuta in questa esecuzione. Restano validi i precedenti controlli di 47 rimandi reciproci e 94 approdi di Alpha4.

I tag rilevati sono *occorrenze testuali*, non conteggi di asset canonici. Tutte le nuove scansioni riportano **zero percorsi feeder-CU elettricamente verificati**. I casi PV2/PV3 e il dettaglio dei dispositivi continuano a richiedere sviluppo.

## Validazione software e integrita'

- 103 test beta3 + 49 test dev14c = **152 test** nel pacchetto.
- Il contenuto di `sld_ci_v04_beta2_dev14c` e' invariato rispetto ad Alpha4.
- Nessun input di test o dato di impianto e' stato usato per impostare conteggi o collegamenti attesi nell'inferenza.
- La scansione e' di **sola lettura** sui PDF. I file in `data\CASE_*` non sono modificati.
- Gli output *non* affermano che la semplice vicinanza a un simbolo dimostri un terminale o un percorso conduttivo.

**Prossima milestone tecnica:** associare regioni/segnali locali al modello di terminali dei dispositivi con topologia interna riconosciuta o confermata, per ottenere il primo percorso completo verificato su un SLD reale. Questo elemento non e' compreso in Alpha5.

### Prova integrata reale aggiuntiva

Eseguito `integrated_cli` sul PDF PV6 completo riutilizzando il baseline dev14c
precedente, con zero coppie FUSED e zero ispezioni CU per isolare la prova del
nuovo router: 4 pagine triagiate, 4 regioni geometriche selezionate entro il
budget di 2 pagine x 2 tag, e integrazione nel file `integrated_report.json`.
Dev14c non e' stato rieseguito ne' modificato. Nessun nuovo arco elettrico e'
stato dichiarato verificato.
