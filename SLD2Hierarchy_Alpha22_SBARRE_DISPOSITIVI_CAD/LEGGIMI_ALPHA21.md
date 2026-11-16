# SLD2Hierarchy — Alpha 21 | QPS CAD e struttura confermata dall'operatore

## Nuovo significato accertato

Il QPS (*Quadro di Parallelo Stringhe*) e' una **String Box** nel CAD Settimo Torinese.
La sigla `QPS-2-4/8`, secondo la spiegazione dell'operatore, significa la
**quarta delle otto String Box dell'inverter 2**. Questa numerazione e'
una convenzione del documento: **NON** e' una regola universale per tutti gli SLD.

L'operatore ha inoltre verificato **1 CU, 1 TR e 3 inverter centralizzati in
parallelo a valle del TR**. Il vecchio file TXT con `16` SB/inverter era errato;
il riferimento corretto separato si trova in `examples/SETTIMO_GROUND_TRUTH_CORRETTA_ESTERNA.txt`.

## Che cosa riconosce autonomamente Alpha 21

1. Tre moduli di conversione candidati tramite geometria dei simboli CAD.
2. Tre campi DC candidati e 24 compartimenti geometrici con sbarra rossa e protezione verde.
3. Con **Tesseract offline opzionale**, le tre sequenze complete di etichette
   QPS 1..8 (8 per gruppo), lette in una sola passata OCR sulla zona interessata.
4. Le 3 corrispondenze geometriche tra modulo grafico e campo, come *candidate*.
5. Nessun collegamento TR–INV automaticamente verificato fino ad attraversare
   apparecchi di protezione; nessuna inferenza obbligatoria 1 TR -> 2 inverter.

Il TXT di Ground Truth non e' mai un input del motore. Non viene aggiunto alcun
numero da un dato teorico o dall'operatore; l'operatore conferma solo la semantica
QPS=String Box e la relazione gerarchica CU/TR/INV.

## Uso su Windows

**Interfaccia unica**: `AVVIA_SLD2HIERARCHY.bat`.

- Scegli il PDF. La diagnostica CAD ora usa Alpha21.
- Per generare **solo evidenze QPS**: scegli **No** alla richiesta di review.
  Il risultato include `alpha21_qps_staging.csv` e `alpha21_diagnostica_qps.json`,
  ma non inventa CU/TR/INV, non produce un Excel SAP certificato.
- Per usare la gerarchia di Settimo **già verificata dall'operatore**: scegli
  **Si** e seleziona `examples/SETTIMO_TOP_SCHEMA_CONFERMATO_OPERATORE.json`.
  La review e' valida **solo per il PDF il cui SHA-256 e' registrato**: file
  PDF diverso o modificato = errore esplicito, non uso silenzioso.
- Con review coerente, vengono creati `alpha21_gerarchie_stereotipi.xlsx`,
  `alpha21_CU_TR_INV_STR_Box.csv`, `alpha21_evidenze.csv` e report JSON.
- `STR_Box` deriva dalle **etichette QPS complete e dai cabinet CAD**, mentre
  CU/TR e proprieta' dell'inverter derivano dalla **conferma operatore**.
- Il foglio Evidenze distingue queste due provenienze.

**CLI (utile per automatizzazione)**:

```powershell
python -m sld_ci_v04_beta3.alpha21_cli --pdf "C:\SLD\PV13_Settimo_Torinese.pdf" --plant-id PV13_Settimo_Torinese --out "reports\settimo" --review-json "examples\SETTIMO_TOP_SCHEMA_CONFERMATO_OPERATORE.json"
```

L'OCR richiede Tesseract installato localmente, disponibile nel PATH o in
`C:\Program Files\Tesseract-OCR\tesseract.exe`. Il programma non usa rete o
servizi esterni. Se Tesseract manca, la geometria resta disponibile ma i QPS
non possono essere dichiarati completamente letti. **Non utilizzare il TXT
per riempire automaticamente i valori mancanti**.

## Risultati effettivi su Settimo

| CU | TR | INV | STR_Box |
|---:|---:|---:|---:|
| 1 | 1 | 1 | 8 |
| 1 | 1 | 2 | 8 |
| 1 | 1 | 3 | 8 |

Totale: **24 QPS/String Box**, non 48. I 3 parent TR sono `CONFERMATO_HITL`
(conferma tecnica dell'operatore), mentre la continuita' elettrica TR -> inverter
rimane `NON VERIFICATA AUTOMATICAMENTE`. L'output e' **STAGING**, non ancora
tracciato di import certificato per Matrix FLOW.

## Sicurezze e regressione

- Il riconoscitore non legge il TXT corretto né quello precedente.
- La review e' circoscritta a **impianto + hash PDF + singoli gruppi QPS**.
- La review non contiene mai le quantita' QPS (vengono ricavate dal PDF).
- Etichette duplicate/incomplete, OCR assente, cabinet incompleti, numero
  inverter incoerente, review parziale o riferita ad altro PDF => non certificare.
- Gli inverter per TR sono **1..N**, senza un rapporto fisso o un limite di due.
- Alpha12/15/16 e i riconoscitori precedenti sono preservati.

## Gap residui

La correlazione delle etichette QPS con i campi CAD e' source-grounded ma
non dimostra da sola la continuita' completa attraverso tutti i componenti.
Sono ancora aperti: percorso elettrico TR–INV automatico su piu' stili CAD,
identificazione degli altri asset SAP richiesti e import provato in Matrix FLOW.
Per CAD differenti non applicare automaticamente la convenzione QPS-n-k/N:
serve una nuova conferma della semantica dei codici o un'esplicita verifica documentale.
