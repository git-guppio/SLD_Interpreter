# SLD2Hierarchy — Alpha 15 / riconoscimento multistile (sperimentale)

## Obiettivo e limiti

Alpha 15 estende il riconoscimento documentale a una **seconda famiglia di convenzioni CAD**, senza modificare il motore Alpha 12/13 già usato su PV11 Pampa Norte.

Il riconoscitore seleziona **in automatico** il metodo a seconda delle etichette presenti:

- `C 1`, `I 1.1`, `TRANSFORMER 1.700 kVA`, `10 STRING BOX` → precedente percorso Alpha 12 (Pampa Norte).
- Codici indicizzati come `ABC-TPO-01-01`, `ABC-INV-01-01`, `ABC-CST-01-I01-20-01` → nuovo percorso Alpha 15 (presente in PV5/PV6/PV7). Il prefisso `ABC` è esemplificativo, non un elenco codificato di impianti.

**Non è un interprete universale:** uno SLD senza etichette compatibili può ancora non essere riconosciuto. Sono richieste ulteriori generalizzazioni per PV8 e lettura grafica/OCR per documenti senza testo nativo come PV3 e Settimo Torinese.

## Come provarlo su Windows

1. Conservare Alpha 14 e le versioni precedenti in altre cartelle.
2. Estrarre il nuovo archivio completo Alpha 15.
3. Avviare `AVVIA_SLD2HIERARCHY.bat` con doppio clic oppure da PowerShell:

   ```powershell
   .\AVVIA_SLD2HIERARCHY.bat
   ```

4. Scegliere `1 Analizza SLD`, selezionare il PDF (in prima battuta `PV5.pdf`, `PV6.pdf` o `PV7.pdf`) e avviare.
5. Il metodo è scelto automaticamente. I report vengono salvati sotto `reports\sap_alpha15\<ID>\<esecuzione>`, **senza sovrascrivere quelli precedenti**.
6. La verifica visiva Alpha 13 resta disponibile per il **vecchio percorso Alpha 12**, ma **non è ancora compatibile con le evidenze multipagina Alpha 15**. Gli output Alpha 15 si verificano con Excel/PDF e non con i pulsanti HITL Alpha 13.

## Output della nuova modalità

- `alpha15_CU_TR_INV_STR_Box.csv` — quattro colonne. `INV` riparte da 1 per ogni trasformatore candidato.
- `alpha15_gerarchie_stereotipi.xlsx` — Dettaglio, Riepilogo, Controlli CU, Evidenze. Verde = cardinalità ricorrente, **non connessione elettrica verificata**.
- `alpha15_evidenze.csv` — riferimenti originali e stato di ogni attribuzione.
- `alpha15_diagnostica.json` — tracciabilità completa e anomalie.

**String Box:** il software conta identificativi distinti e seriali `1..N` per ciascun inverter. Il numero `20` in `20 STRINGS` indica stringhe per cassetta e **non** il numero di cassette. Se nella sequenza manca un numero, `STR_Box` resta vuoto e il candidato massimo compare solo nella diagnostica.

**Parent TR–inverter:** un collegamento suggerito da codici con stesso prefisso, CU e progressivo rimane `CANDIDATO_PER_CODIFICA`. Nessuna continuità elettrica è stata verificata automaticamente. Non c'è limite massimo di inverter per trasformatore: quando il legame non è evidente, resta irrisolto.

## Risultati iniziali, non ancora certificati contro Ground Truth

| Documento | CU | TR candidate | Inverter | Sequenze box complete | Anomalie |
|---|---:|---:|---:|---:|---|
| PV5 | 7 | 13 | 13 | 12/13 | una sequenza con seriale mancante |
| PV6 | 2 | 3 | 3 | 3/3 | nessuna rilevata |
| PV7 | 1 | 2 | 2 | 1/2 | una sequenza con seriale mancante |

I documenti PV5, PV6 e PV7 condividono **la stessa famiglia di codifiche**. Questi dati dimostrano un secondo metodo di lettura, non tre convenzioni SLD indipendenti. Le quantità e le appartenenze richiedono verifica sul PDF e, dove disponibile, contro una Ground Truth separata.

## Test

`run_tests.bat` esegue i test beta3 + dev14c. La versione Alpha 15 include nove nuovi test di unità su lettura indicizzata, seriali mancanti, distinzione stringhe/cassette, scope e output. Il codice del motore precedente è mantenuto invariato.

## Per il responsabile

Presentare la PoC come **dimostratore con due famiglie documentali riconosciute**, Excel SAP-oriented, evidenze e problemi esplicitamente tracciati, non come interprete automatico universale. Le prossime milestone sono validazione indipendente di PV5/6/7, gestione semantica PV8 e vettoriale/OCR per Settimo.

## Materiale di esempio

La cartella `examples/ALPHA15_MULTI_SLD` contiene gli Excel/CSV/JSON prodotti con PV5, PV6 e PV7, per confronto prima della prova sul PC. Il PDF `examples/ALPHA15_Nota_Responsabile.pdf` riassume i risultati, i limiti e la milestone successiva.

Il lanciatore `AVVIA_SLD2HIERARCHY_ALPHA14_LEGACY.bat` conserva l'interfaccia precedente per sicurezza. `AVVIA_SLD2HIERARCHY.bat` usa Alpha 15.
