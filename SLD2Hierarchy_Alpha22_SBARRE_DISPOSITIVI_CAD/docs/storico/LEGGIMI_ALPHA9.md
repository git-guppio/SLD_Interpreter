# SLD2Hierarchy beta3 — Alpha 9 (SAP-FIRST, primo incremento)

**ATTENZIONE**: NON è una PoC SAP completa e NON genera ancora le Functional
Locations. Raccoglie e controlla la gerarchia che il motore Alpha8/dev14c
è già capace di proporre, prepara i dati da mappare sul vero Matrix Flow e
produce le verifiche HITL necessarie, senza creare asset mancanti.

## Comandi Windows PowerShell

Estrarre lo ZIP in una cartella NUOVA. Da PowerShell nella cartella:

```
.\run_tests.bat
.\prepara_gerarchia_SAP.bat
```

La nuova procedura propone due ingressi:

1. `dev14c_inference.json` GIA' prodotto, che deve contenere **l'inferenza
   COMPLETA** (non il solo `integrated_report.json`). È la strada veloce.
2. Nuovo `SLD.pdf`, con eventuale `LAYOUT.pdf`, per una nuova inferenza
   documentale. Questo può richiedere diversi minuti. Per PDF privo di testo
   nativo viene usato il comportamento OCR `auto` del motore esistente.

Il programma NON richiede feeder. Non passa le quantity della Ground Truth
all'inferenza; non inventa device per soddisfare il minimo 1.

Output `reports\sap_alpha9`:

- `sap_hierarchy_alpha9.csv`: tabella delle identità SAP candidate riconciliate,
  con parent, tipo, provenienza e stato.
- `sap_hierarchy_alpha9.json`: anche quantità per tipologia, stato e riferimenti
  alle associazioni TR–inverter confermate.
- `sap_hitl_tasks_alpha9.csv`: interrogativi necessari per i minimi e i parent.
- `sap_operator_review_TEMPLATE.json`: schema per le conferme esplicite;
  NON contiene conferme per default.

### Come applicare conferme HITL

Copiare il file template ed inserire, con evidenza verificabile, oggetti in
`confirmed_assets`:

```
{"asset_id":"CU1::IOCB_1","entity_type":"IOCB",
 "parent_id":"CU1","evidence_ref":"SLD:p3:etichetta IOCB1"}
```

Il parent_id deve esistere nella baseline oppure essere stato confermato
esplicitamente nello stesso file. L'identificativo dell'impianto deve
coincidere. Il sistema rifiuta identità duplicate e parent non validi.

Per indicare connessioni TR/inverter opzionali, usare
`confirmed_transformer_inverter_links`, con transformer_id, inverter_id,
secondary_index (1 o 2 quando noto), evidence_ref. Una coppia con lo stesso
secondario è rifiutata, ma 1 TR può avere più inverter associati.

```
python -m sld_ci_v04_beta3.sap_cli --inference-json "C:\...\dev14c_inference.json" --review-json "C:\...\conferme_pv8.json" --out-dir "reports\sap_alpha9_pv8"
```

Nota: nella prima iterazione le conferme sono **asset espliciti**, non soli
conteggi numerici. Per ridurre il carico operativo sui nuovi SLD si prevede
una UI HITL raggruppata e una procedura di conferma di quantità per blocchi,
ancora da sviluppare e validare.

### Sperimentazione svolta

Su un precedente report dev14c completo relativo a PV8, **senza nuova lettura
del PDF**, sono state mantenute 55 CU, 110 TR LV/MV, 220 inverter e 1.320
String Box. 55 posizioni IOCB e 220 posizioni LV/LV rimangono senza identità
risolta: in totale 275 verifiche puntuali, raggruppabili in 2 categorie.
NON significa che questi dispositivi siano fisicamente assenti.

### Limiti

- I conteggi derivano dall'inferenza esistente: NON sono stati corretti o
  certificati da Alpha9; nessuna misura precision/recall nuova.
- Le associazioni elettriche TR/inverter NON sono dedotte dai soli numeri.
- Nessun codice FL, nessun import SAP, nessuna compatibilità Matrix Flow
  verificata: il formato tabellare è un **CONTRATTO DI STAGING PROVVISORIO**.
- Non esiste ancora un ciclo interattivo completo di review: il template può
  essere editato e passato al CLI per applicare conferme tracciate.
- Le policy di riservatezza aziendale devono essere rispettate prima di
  caricare documenti SLD non oscurati su servizi esterni.

## Preparazione nuovi SLD e confronto indipendente

`examples/SAP_GROUND_TRUTH_TEMPLATE.csv` e' un modello semplice da compilare
prima dell'analisi: una riga per categoria nel contesto PLANT, CU o INVERTER.
Lasciare vuoto ogni valore NON NOTO. Distinguere quantity_known da
quantity_graphically_drawn. Il motore NON legge questo CSV per decidere i
risultati: servirà dopo, come Ground Truth indipendente.

Ulteriori CSV prodotti:

- `sap_scope_counts_alpha9.csv`: quantità di **identità risolte** per singola CU
  e inverter. Un valore 0 segnala che nessun ID è stato risolto, NON che il
  dispositivo fisicamente non esista.
- `sap_hitl_groups_alpha9.csv`: raggruppa le verifiche per tipologia, per
  evitare di leggere centinaia di righe una alla volta.
