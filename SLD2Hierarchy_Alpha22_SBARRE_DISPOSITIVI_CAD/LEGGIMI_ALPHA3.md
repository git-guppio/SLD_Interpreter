# SLD2Hierarchy beta3 — Integrated Alpha 3

**Scopo:** identificare rimandi fra fogli e sottocampi *reciproci*, verificabili tramite due citazioni indipendenti, senza attribuire loro indebitamente una connessione elettrica fisica. Prosegue la gerarchia e le membership strutturali/documentali già prodotte da dev14c, invariato.

## Test di regressione

Apri PowerShell nella cartella estratta ed esegui `cmd /k ".\run_tests.bat"`: 81 test beta3 + 49 test dev14c = **130** test attesi.

## Diagnostica rapida, senza rielaborare i 55 fogli di PV8

Apri `diagnostica_rimandi_PDF.bat` (oppure `cmd /k ".\diagnostica_rimandi_PDF.bat"`) e fornisci **il file `dev14c_inference.json` già prodotto**, non il PDF e non l'`integrated_report.json`.

Salva `reports\cross_sheet_reference_graph.json` e `reports\cross_sheet_reference_graph.csv` separatamente dagli input. Nessun file sorgente o CASE viene modificato.

Il comando `esegui_integrazione.bat` continua a funzionare come in Alpha 2: il nuovo `integrated_report.json` comprende anche `beta3_cross_sheet_references`.

## Evidenze e limiti

- Un riferimento va associato a una **pagina con un'unica identità sorgente** ricavata da `SOURCE_INSTANCE`, e a una CU di destinazione **canonica nel medesimo impianto**. Se la pagina è ambigua non viene scelta una CU arbitrariamente.
- Servono due riferimenti **indipendenti e coerenti**, il primo verso la CU di destinazione (es. `A...` / `TO...`), il secondo sul foglio di destinazione (es. `DE...` / `FROM...`). Riferimenti senza direzione o duplicati rimangono irrisolti.
- Gli 8 gruppi eventualmente ricostruiti sono gruppi di **rimandi documentali**. NON dimostrano che esista una continuità conduttiva, NON stabiliscono il nome reale del feeder e NON rappresentano una verifica attraverso gli interruttori/celle MT.
- Il confronto con le membership `INFERRED` di layout è **solo successivo** alla ricostruzione, per diagnostica; non determina gli archi.
- Direzioni `A`/`DE` descrivono la continuità dei rimandi tra fogli; NON sono una verifica del verso di flusso di potenza.
- Il tool non accede ad alcun file benchmark/oracolo Ground Truth, né impiega conteggi attesi per creare i gruppi.

## Verifica eseguita sui file PV8 del progetto (15 ottobre 2026)

Con l'inferenza dev14c e i PDF PV8 analizzati in questa sessione, il modulo trova **47** link documentali reciproci e **8** gruppi (dimensioni 7,7,7,7,7,7,7,6). Tutti e 47 i link sono concordi con la membership di layout di dev14c; **0** verifiche elettriche feeder-CU.

Il caso sintetico dei test copre ambiguità e conflitti; le misure PV8 sono osservazioni sul documento, non costanti del software.
