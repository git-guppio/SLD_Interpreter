# Alpha 19 – Ipotesi grafiche controllabili e percorso verso SLD2Hierarchy operativo

## Cosa e' stato implementato

Sui PDF CAD **privi di testo nativo**, il motore Alpha 18 riconosce moduli di
conversione candidati e campi grafici inferiori. Alpha 19 aggiunge un passaggio
**conservativo di correlazione visiva** tra i due livelli:

- Ordina le due serie sulla stessa pagina e formula una corrispondenza 1:1
  **solo quando** entrambe hanno almeno due elementi, stessa numerosità,
  rettangoli distinti e campi effettivamente a valle in verticale.
- Non opera se le serie non coincidono, sono sovrapposte o si trovano su
  pagine diverse. L'assenza di una proposta e' preferibile a una falsa gerarchia.
- Conserva coordinate, quantità di rami osservati e numero di compartimenti
  grafici per ogni ipotesi.
- Non identifica questi compartimenti come **String Box**, non associa
  automaticamente un trasformatore, non attribuisce una CU e non certifica
  la continuità elettrica.
- Non usa Ground Truth, file TXT, nomi impianto, proporzioni inverter/TR fisse.

Sui documenti nativi PV11, PV5/6/7 e PV8 restano attive le modalità precedenti.
Il motore dev14c e i riconoscitori Alpha12/15/16/18 non sono stati riscritti.

## Esecuzione

Esegui `AVVIA_SLD2HIERARCHY.bat` dalla cartella estratta; per un CAD senza
etichette native il workbench lancia Alpha19 anziché Alpha18. L'avvio separato,
se necessario, e' `DIAGNOSTICA_CAD_ALPHA19.bat`.

Da PowerShell, senza interfaccia:

```powershell
python -m sld_ci_v04_beta3.alpha19_cli --pdf "C:\\input\\schema.pdf" --out "reports\\cad_alpha19"
```

Risultati principali:

- `alpha19_correlazioni_grafiche.csv`: proposte grafiche e campi SAP volutamente
  vuoti dove non dimostrabili;
- `alpha19_ipotesi_grafiche.json`: tutte le evidenze con motivi delle astensioni;
- `alpha19_anteprima_associazioni_p1.png`: marcature sul PDF originale;
- i precedenti report Alpha18 rimangono disponibili per compatibilità.

## Risultati provati – Settimo/PV3

Entrambi i documenti mostrano tre moduli candidati e tre campi a valle; Alpha19
propone tre accoppiamenti **per ordine spaziale**. Ognuno mostra otto rami e
otto compartimenti grafici; il fatto che questi numeri coincidano **non prova**
una connessione né dimostra 8 o 16 String Box. La quantità String Box resta
`null`. Le due tavole sono quasi duplicate: NON costituiscono validazione su
stili indipendenti.

## Sicurezza e compatibilità

- File PDF originali in sola lettura;
- nessuna API esterna o OCR introdotta;
- nessuna promozione automatica a asset/gerarchia SAP verificata;
- nessun rapporto preimpostato 1:2 tra trasformatori e inverter;
- `328` test automatizzati (beta3 `279` + dev14c `49`), inclusi 12 nuovi;
- gli output ricalcolati rimangono distinti dai documenti di Ground Truth.

## Per il percorso verso il prodotto finale

Consulta `ROADMAP_PRODOTTO_ALPHA19.md`. Un interprete utile non deve riconoscere
"qualunque PDF" mediante congetture: deve interpretare gli schemi supportati,
dichiarare cio' che non sa interpretare e aprire verifiche HITL specifiche.
