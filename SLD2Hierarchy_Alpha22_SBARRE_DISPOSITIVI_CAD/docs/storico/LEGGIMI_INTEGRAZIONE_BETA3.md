# SLD2Hierarchy — Beta3 integrazione controllata (15 ottobre 2026)

## Cos'è questa consegna

Il nuovo comando `esegui_integrazione.bat` **esegue realmente** l'analisi completa del PDF SLD e, se disponibile, del PDF layout attraverso la pipeline `dev14c` esistente. In seguito beta3 seleziona automaticamente le coppie di simboli dello SLD che hanno tag, fusione testo+simbolo e terminali candidati; crea aree di studio e prova la continuità geometrica esterna ai dispositivi. La selezione delle coppie **non** presume una relazione elettrica.

Non è una beta3 produttiva conclusa: le conclusioni di dev14c restano indipendenti, mentre le prove beta3 sono diagnostiche. **Zero tracciamenti feeder→CU verificati da beta3 su PV6/PV7 reali.** Nessun valore dei benchmark PV4/PV8 è passato agli algoritmi.

## Utilizzo Windows

1. Estrai questo ZIP in una cartella dedicata sotto `SLD2Hierarchy\prototype`, senza sovrascrivere gli altri pacchetti.
2. Avvia PowerShell all'interno della cartella estratta.
3. Esegui `cmd /k ".\run_tests.bat"` (esegue le suite beta3 e dev14c).
4. Per elaborare un impianto reale, esegui `cmd /k ".\esegui_integrazione.bat"` e inserisci il percorso del **file** `*_SLD.pdf`, l'eventuale file `*_LAYOUT.pdf` e l'identificativo impianto.
5. Leggi il riepilogo a video e i due output sotto `reports\integrated_run\`:
   - `dev14c_inference.json` — risultato completo della pipeline dev14c, separato e invariato dalle prove beta3;
   - `integrated_report.json` — riepilogo gerarchia/membership dev14c e prove geometriche locali beta3.

Per PV8, i tuoi due file separati possono essere selezionati come `...\data\CASE_008_PV8\input\PV8_SLD.pdf` e `...\data\CASE_008_PV8\input\PV8_LAYOUT.pdf`; `plant_id=PV8`. Non inserire una cartella al posto di un PDF. **Il run sulle 55 pagine SLD può richiedere diversi minuti**, molto più dei test automatici.

Esecuzione diretta senza input interattivi:

```powershell
python -m sld_ci_v04_beta3.integrated_cli --sld "C:\\percorso\\impianto_SLD.pdf" --layout "C:\\percorso\\impianto_LAYOUT.pdf" --plant-id PV8 --out-dir "reports\\integrated_run"
```

Se non esiste un layout, ometti `--layout`. La modalità `--max-pages N` serve **solo** allo smoke test e il report apparirà `PARTIAL` quando non sono state elaborate tutte le pagine. Non utilizzare report parziali per confronti con regression oracle.

## Cosa abbiamo verificato qui

- **62 test beta3 + 49 test dev14c = 111 test superati**.
- **PV7.pdf**: tutte le 3 pagine analizzate, dev14c produce 1 CU, 2 MV/LV TR, 2 inverter, 25 SB. Beta3 studia una coppia di simboli reali e non trova un percorso interno alla sola ROI.
- **PV6.pdf**: tutte le 4 pagine analizzate, dev14c produce 2 CU, 3 MV/LV TR, 3 inverter, 35 SB. Beta3 studia due coppie reali senza provare una connessione nell'area analizzata.
- Questi conteggi sono **output d'inferenza, non confronti con Ground Truth**: non è corretto dichiararli veri senza ulteriori verifiche.
- Su PV7 e PV6 il problema iniziale di mancato aggancio ai terminali dipendeva in parte dal taglio dei segmenti che attraversavano il bordo della ROI. Il nuovo `geometry/roi.py` conserva il tratto interno, registra i tagli artificiali e nega qualsiasi prova di connettività globale attraverso il bordo.
- `sld_ci_v04_beta2_dev14c/` è byte-per-byte uguale ai 78 file contenuti nel Bootstrap 5.

## Legenda dei risultati

- `COMPLETE_INTEGRATION_DIAGNOSTIC`: le pagine richieste sono state elaborate; **non** significa che un grafo elettrico o un feeder sia completamente verificato.
- `PARTIAL`: pagine non analizzate o errori nel processo.
- `FUSED`: dev14c ha trovato un candidato simbolo+testo; non significa un asset accettato.
- `LOCAL_GEOMETRIC_PATH_CANDIDATE`: solo continuità geometrica locale, non appartenenza a feeder.
- `DISCONNECTED_IN_ROI`: nessun percorso nella porzione analizzata; un percorso esterno alla ROI può esistere.
- `UNRESOLVED`: cap, terminali non associabili, bordo artificiale o altra ambiguità.
- `legacy_documental_membership` e `legacy_graph_verification`: **due risultati distinti** dal dev14c congelato. `beta3_graph_verified_feeder_membership` resta zero se la nuova verifica non raggiunge un feeder identificato e la CU.

## Vincoli preservati

- Nessuna lettura del Ground Truth o delle cifre benchmark come input dell'inferenza.
- Nessun hardcoding specifico PV4/PV8, e nessun riuso di conoscenza d'impianto senza un esplicito knowledge store.
- Gli input PDF non vengono modificati; i CASE non vengono scritti automaticamente. Gli output vanno nella directory specificata.
- L'eventuale knowledge store passato contemporaneamente a feedback operatore viene prima copiato in una directory di output: la sorgente non viene alterata.
- Segmenti corti conservati salvo motivi contestuali; dispositivi interposti non attraversati automaticamente.
- Gli eventuali segmenti interrotti dal bordo della ROI vengono conservati con provenienza ma **non** diventano terminali elettrici reali.

## Prossimo problema tecnico dimostrato

La continuità locale tra simboli vicini ancora non si risolve sui due SLD: serve associare topologicamente i terminali alle sbarre e ai circuiti corretti su un grafo più ampio, mantenendo i dispositivi interposti e tracciando l'origine dei segmenti. Prima di proclamare la fine del progetto, eseguire un confronto quantitativo a posteriori su PV4 e PV8 **completi**, e prove su impianti non usati per sviluppare le euristiche.
