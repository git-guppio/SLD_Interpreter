# SLD2Hierarchy — Alpha 12 | Gerarchie stereotipate e output SAP (06/11/2026)

## Cosa cambia

**Alpha 12 aggiunge un esportatore automatico per gli SLD di impianti fotovoltaici con inverter CENTRALIZZATI.** Non modifica il precedente motore `dev14c` né Alpha 10/11. Il suo obiettivo è lo staging dei conteggi e delle gerarchie per Matrix Flow; **non** l'import SAP definitivo.

Tabella esatta, una riga per inverter riconosciuto: `CU | TR | INV | STR_Box`.

- `CU`: indice CU originale del documento.
- `TR`: numero del trasformatore associato (candidato o confermato).
- `INV`: **indice rinumerato 1..N dentro il TR**, non l'identificativo originale dello SLD; ricomincia da 1 al cambio di TR.
- `STR_Box`: quantità **indicata nel PDF per quell'inverter**, non capacità di targa. I valori mancanti o contraddittori rimangono **vuoti**, mai zero. Un'etichetta quantitativa non equivale al riconoscimento di ogni singola SB.

### Stereotipi

La cardinalità TR/CU prevalente viene calcolata dai dati documentali; lo stesso accade per la cardinalità INV/TR. Il programma **non impone mai** 2 TR/CU o 2 INV/TR: un trasformatore può avere **1 o N** inverter. Il valore prevalente esiste soltanto con almeno due istanze e maggioranza stretta tra quelle osservate; senza evidenza sufficiente è indeterminato.

- **Verde**: elemento conforme alla cardinalità prevalente riconosciuta nell'impianto;
- **Arancione**: eccezione rispetto alla cardinalità prevalente;
- **Grigio**: dato incompleto, parent non identificato o stereotipo non dimostrabile.

**Il verde NON certifica il collegamento elettrico né la conformità SAP.** Una relazione TR→INV geometrica rimane una proposta fino a conferma HITL. Il foglio `Evidenze` conserva i due stati distinti e l'eventuale conflitto di etichetta (CU19 Pampa Norte).

## Prova rapida in Windows PowerShell

1. Estrarre lo ZIP in una cartella nuova, senza sovrascrivere Alpha 11.
2. Eseguire `run_tests.bat` per la regressione.
3. Eseguire `esporta_gerarchia_stereotipi_PDF.bat`.
4. Inserire PDF completo, `PV11_Pampa_Norte` e premere INVIO nel campo JSON HITL per una prima elaborazione delle proposte **non confermate**.

Il report viene generato in:
`reports\sap_alpha12\PV11_Pampa_Norte\`.

| File | Funzione |
|---|---|
| `alpha12_CU_TR_INV_STR_Box.csv` | Import tecnico: sole 4 colonne, separatore `;` UTF-8 BOM |
| `alpha12_gerarchie_stereotipi.xlsx` | 4 fogli Excel, verde/ambra/grigio |
| `alpha12_evidenze.csv` | Una riga per inverter, con asset originali, evidenze e status |
| `alpha12_riepilogo.json` | Diagnostica completa, conteggi, anomalie, criteri |
| `alpha10_*` / `alpha11_*` | Diagnostiche originali del motore precedenti preservate |

**Fogli Excel**: `Dettaglio`, `Riepilogo`, `Controlli CU`, `Evidenze`.

Se hai approvazioni HITL **corrette e limitate alle CU effettivamente verificate**, fornisci il loro JSON approvato quando richiesto. Non presentare una verifica della sola CU19 come evidenza sufficiente per confermare gruppi estesi a tutte le 22 CU.

### Prova senza rileggere il PDF

Se possiedi i report Alpha 11 generati sul tuo PC:

```powershell
python -m sld_ci_v04_beta3.sap_stereotypes_cli `
 --alpha10-json ".\reports\sap_alpha11\PV11_Pampa_Norte\alpha10_hierarchy_review.json" `
 --alpha11-json ".\reports\sap_alpha11\PV11_Pampa_Norte\alpha11_parent_proposals.json" `
 --plant-id PV11_Pampa_Norte `
 --out-dir ".\reports\sap_alpha12\PV11_Pampa_Norte"
```

Il report Alpha10 deve riferirsi allo stesso SLD/impianto di Alpha11.

## Cosa aspettarsi per Pampa Norte

In modalità **senza HITL**: 22 CU, 44 TR candidati, 88 inverter, 88 righe CSV, somma di 923 String Box documentate, 2 TR/CU e 2 INV/TR uniformi, `parent confermati HITL = 0`, 88 proposte TR→INV. La quantità individuale della CU2 deve essere letta dal PDF, con 10 SB su INV originale 3 e 11 su INV originale 4.

Per CU1, la tabella diventa:

```text
CU;TR;INV;STR_Box
1;1;1;10
1;1;2;10
1;2;1;11
1;2;2;10
```

Per CU2, TR2, la rinumerazione fa corrispondere gli INV originali 3 e 4 ai nuovi INV 1 e 2, rispettivamente 10 e 11 SB.

## Limiti importanti

- Il riconoscitore Alpha10/11 utilizza etichette native e geometria locale del PDF. Non ha ancora copertura automatica sufficiente per SLD senza testo, come Settimo Torinese.
- Le quantità String Box sono valori documentari, non verifiche per tracciamento conduttori.
- Un rapporto di ripetitività **non** può essere usato per fabbricare dispositivi o assegnare parent mancanti.
- Nessuna nuova regola si estende automaticamente a impianti di altra tecnologia. Bastardo è **fuori ambito**.
- Per il momento non vengono generati le FL SAP definitive, l'import Matrix Flow o i nodi IOCB/LV/LV mancanti.
- L'XLSX è generato dal solo Python standard library (OOXML): non richiede installazione di librerie Excel aggiuntive su Windows.
