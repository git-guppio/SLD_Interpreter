# SLD2Hierarchy — Alpha 14, unico punto di accesso

## Scopo

Alpha 14 semplifica il flusso SAP-first per **impianti FV con inverter centralizzati**. Non introduce nuovi algoritmi di riconoscimento: conserva il motore di Alpha 12, le evidenze e la verifica visuale individuale di Alpha 13. I report restano **STAGING**, non tracciati Matrix FLOW certificati.

## Avvio Windows

1. Estrarre lo ZIP in una **nuova cartella**, senza eliminare Alpha 12 o Alpha 13.
2. Aprire PowerShell nella cartella ed eseguire ` .\AVVIA_SLD2HIERARCHY.bat ` (oppure doppio clic sul `.bat`).
3. Appare una sola finestra iniziale con quattro comandi:

- **1 — Analizza nuovo SLD:** con *Scegli PDF* si seleziona il PDF; il codice impianto viene proposto dal nome file ed è modificabile. Cliccare *Analizza nuovo SLD*. Il motore genera Excel, CSV e registro Evidenze. Il report attivo si aggiorna automaticamente.
- **2 — Verifica visivamente:** usa il report attivo oppure il pulsante *Scegli report* per aprirne uno esistente (inclusi quelli Alpha 12 GUI / Alpha 13). Il programma usa il PDF sorgente registrato nel report se il file esiste ancora, altrimenti lo richiede con una finestra. Il visualizzatore permette di confermare **una riga per volta** o annotare *Da correggere*.
- **3 — Rigenera Excel con conferme HITL:** richiede un report con verifiche visive **confermate**, generate dal visualizzatore Alpha 13 e riferite esattamente al PDF e al report originali. Produce un nuovo report separato. Le sole note *Da correggere* non modificano l'Excel.
- **Riepilogo prove su più SLD:** crea un `RIEPILOGO_PROVE_SLD.csv` con una riga per **esecuzione completa** effettuata con Alpha 14. Un conteggio estratto dal PDF non equivale a un conteggio accurato e convalidato; la conformità Matrix FLOW resta **NO**.

## Dove sono salvati i risultati

`reports/sap_alpha14/<impianto>/<data_ora>/`

Una cartella di esecuzione contiene `alpha12_gerarchie_stereotipi.xlsx`, `alpha12_CU_TR_INV_STR_Box.csv`, `alpha12_riepilogo.json`, `alpha12_evidenze.csv` e, se effettuate, le verifiche Alpha 13. **Ogni avvio crea un nuovo sottodirettorio**, senza sovrascrivere quelli precedenti. Se due esecuzioni avvengono nello stesso secondo viene aggiunto un suffisso.

Nell'Excel:
- `Dettaglio`: **CU | TR | INV | STR_Box**, una riga per inverter riconosciuto; INV riparte da 1 per TR;
- `Riepilogo` e `Controlli CU`: cardinalità ripetute ed eccezioni;
- `Evidenze`: riferimenti PDF, provenienza e stato delle associazioni.

**Il verde indica una cardinalità ripetuta, non la continuità elettrica dimostrata.** Le associazioni TR–INV senza conferma sono candidate. Quantità SB assenti restano irrisolte, senza numeri inventati.

## Verifica su altri SLD già archiviati

Dalla stessa finestra eseguire **Analizza nuovo SLD** su ciascun PDF, assegnando **identificativi differenti** agli impianti; poi cliccare **Riepilogo prove su più SLD**. Per una misura attendibile dell'efficacia è necessario confrontare anche il risultato per ogni dispositivo con una Ground Truth indipendente, tenuta fuori dagli input dell'algoritmo. Il riepilogo da solo mostra la *copertura documentale*, non la precisione.

Il PDF di Settimo Torinese è un caso limite noto: nessun testo nativo, quindi la diagnostica può produrre 0 CU/INV e indicare necessità OCR/HITL; non attribuire automaticamente quantità ricavate dal TXT di riferimento. Il lavoro esclude gli impianti FV con inverter di stringa.

## Sicurezza e regressione

- Nessuna API o servizio esterno; i dati restano sul PC.
- `run_tests.bat` esegue tutta la regressione beta3 + dev14c, inclusi i test del nuovo flusso.
- I vecchi `.bat` continuano a funzionare come alternativa.
- In caso di errore GUI Windows, eseguire `AVVIA_ALPHA12_CON_FINESTRA.bat` e `AVVIA_VERIFICA_VISIVA_ALPHA13.bat`.
- La GUI usa `tkinter` standard; l'apertura effettiva va provata sul Windows dell'utilizzatore.
