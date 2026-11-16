# SLD2Hierarchy beta3 Integrated Alpha 2 — 15 ottobre 2026

## Obiettivo e stato reale

Questa versione **non è ancora un interprete feeder–CU verificato end-to-end**. È una revisione di Alpha 1 che elimina un blocco nella pianificazione delle verifiche geometriche, espone correttamente le membership già ottenute da dev14c e limita esplicitamente il riutilizzo dell'apprendimento operatore all'impianto di origine.

**Non si modificano** i sorgenti di `sld_ci_v04_beta2_dev14c`, i PDF originali o le cartelle CASE. Ground Truth, benchmark e valori attesi non entrano mai nella pipeline d'inferenza. I risultati beta3 geometrici non promuovono automaticamente le membership.

### Cambiamenti principali

1. **Tre livelli indipendenti di membership** in `integrated_report.json → legacy_inference → membership_provenance`:
   - `canonical_cu_feeder_membership_count`: CU assegnate da dev14c, qualunque ne sia la fonte;
   - `structural_inferred_count`: assegnazioni inferite da geometria/layout e riconciliazione;
   - `explicit_schedule_membership_count`: assegnazioni documentate da schedule espliciti;
   - `graph_verified_membership_count`: assegnazioni effettivamente verificate da dev14c sul grafo.
   **Non sommare i livelli come asset distinti.** In particolare lo zero degli schedule non cancella le membership strutturali.
2. **Coda per identità canonica CU**, `beta3_identity_verification_queue`: non richiede due simboli `FUSED`. Ricostruisce testimoni SLD e terminali con identico `anchor_id`, non accetta etichette ripetute in modo arbitrario, registra il feeder strutturale come *evidenza non verificata* e indica la causa che impedisce il percorso elettrico.
3. **Diagnostica automatica della geometria vicino alle CU**, `beta3_cu_neighborhood_inspections`: esamina fino a 3 aree anche in assenza di coppie `FUSED`, conserva i tagli artificiali e non dichiara verificato alcun percorso feeder–CU.
4. **Knowledge store PLANT-scoped**: l'esecuzione ora può chiedere un JSON esistente e crea **solo una copia filtrata** sotto `reports`; i mapping di altri impianti o con scope senza origine verificabile non vengono caricati. Un nuovo feedback operatore privo di `plant_id` corretto viene rifiutato. Nessun knowledge store viene caricato automaticamente.
5. **Riutilizzo rapido del risultato dev14c**: quando hai già `dev14c_inference.json`, passalo tramite `--baseline-json` o lo script batch. La pipeline non ricalcola le decine di pagine già processate. Convalida plant ID, nomi dei file e numero di pagine, **ma non certifica l'identità byte-per-byte dei PDF**; il report segnala esplicitamente questa limitazione. La baseline preesistente rimane invariata. Il riutilizzo non può essere combinato con nuovo knowledge store/feedback.

## Utilizzo Windows

1. Estrai lo ZIP sotto `SLD2Hierarchy\prototype\SLD2Hierarchy_beta3_integrated_alpha2_2026-10-15\`, lasciando le altre versioni intatte.
2. Apri PowerShell in questa cartella ed esegui `cmd /k ".\run_tests.bat"`.
3. Esegui `cmd /k ".\esegui_integrazione.bat"`. Indica file SLD, layout facoltativo, plant ID. Quando richiesto, puoi fornire il percorso completo del vecchio `dev14c_inference.json` per riutilizzarlo: questa è l'opzione più rapida per PV8. Altrimenti premi INVIO e, se desideri riusare apprendimento dello stesso impianto, indica il knowledge store.
4. Il report è `reports\integrated_run\integrated_report.json`.

In alternativa, comando diretto per il riutilizzo della baseline PV8:

```powershell
python -m sld_ci_v04_beta3.integrated_cli `
  --sld "C:\...\data\CASE_008_PV8\input\PV8_SLD.pdf" `
  --layout "C:\...\data\CASE_008_PV8\input\PV8_LAYOUT.pdf" `
  --plant-id PV8 `
  --baseline-json "C:\...\prototype\SLD2Hierarchy_beta3_integrated_alpha1_2026-10-15\reports\integrated_run\dev14c_inference.json" `
  --out-dir "reports\integrated_run"
```

**Attenzione:** `--baseline-json` deve riferirsi a un run dev14c ottenuto sui medesimi documenti: il controllo automatico confronta nomi, impianto e numero di pagine, non il contenuto completo.

## Verifiche condotte

- Test `beta3` e `dev14c` completamente superati nel contesto di sviluppo: **71 + 49 = 120**.
- Esecuzione fresca di Alpha 2 su **PV7.pdf**: tre pagine analizzate; una CU nella coda; nessun percorso feeder–CU verificato.
- Analisi reale del **PV8** da output dev14c fornito dall'utente, verificato in associazione ai PDF SLD/Layout separati da `PV8.pdf`: **55 CU canoniche, 55 membership strutturali inferite, zero schedule espliciti, zero graph-verification**. Coda **55/55 CU**, di cui **54 senza terminale associato allo stesso anchor SLD e 1 con terminale solo candidato**. Tre aree analizzate; nessuna connessione feeder–CU verificata. L'inferenza dev14c completa è stata riutilizzata, non ricalcolata.
- Nessun mapping `Linea 1...8` è disponibile nel knowledge store generico incluso nel package; l'utente dovrà fornire il proprio knowledge store solo se esiste e desidera riutilizzarlo. Il sistema **non lo reinventa**.

## Limiti tecnici ancora aperti

L'ostacolo principale non è più la creazione della coda, ma la corrispondenza fisica tra **CU, simbolo elettrico, terminale MV e feeder root SLD**. Un'identità testuale, un layout, un colore o la vicinanza geometrica non bastano a dimostrare continuità. La prossima milestone è una prova visiva verificabile di un percorso feeder–dispositivo–CU in un SLD reale e, solo dopo, una regressione cross-plant con Ground Truth usata esclusivamente dal valutatore esterno.
