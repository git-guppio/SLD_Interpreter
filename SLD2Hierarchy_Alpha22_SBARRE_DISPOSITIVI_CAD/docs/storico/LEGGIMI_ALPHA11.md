# SLD2Hierarchy Beta3 — Alpha 11 SAP Parentage (6 novembre 2026)

## Scopo

Questo incremento **non sostituisce Alpha10**: aggiunge proposte prudenziali per l'appartenenza **trasformatore LV/MV → inverter centralizzato** partendo dalle etichette native e dalla loro disposizione locale sul PDF. L'obiettivo immediato resta la gerarchia per **Matrix Flow / SAP Functional Locations**, non il grafo elettrico completo.

**Limite essenziale:** una proposta spaziale non prova il percorso conduttivo e non certifica l'asset SAP. Il campo `parent_id` resta vuoto per gli inverter fino a una conferma esplicita dell'operatore. I conteggi minimi non generano asset inesistenti. Le etichette del documento sono l'unico input all'inferenza: il TXT dell'operatore non viene aperto dal motore.

## Avvio in Windows PowerShell

Estrarre in una **nuova directory**, senza sovrascrivere Alpha10:

```powershell
.\run_tests.bat
.\diagnostica_parent_TR_INV_PDF.bat
```

Rispondere al programma:

- PDF: percorso completo di `PV11_Pampa_Norte.pdf` (con `.pdf`);
- Impianto: `PV11`;
- JSON HITL: premere INVIO alla prima elaborazione.

Risultati in `reports\sap_alpha11\PV11\`:

| File | Contenuto |
|---|---|
| `alpha11_parent_proposals.csv` | 1 proposta per inverter con `cu_id`, `inverter_id`, `proposed_transformer_id`, coordinate e origine |
| `alpha11_parent_proposals.json` | Proposte, evidenze, ambiguità e gruppi per HITL |
| `alpha11_review_suggested_groups.csv` | Configurazioni ricorrenti da verificare, con CU esplicitamente elencate |
| `alpha11_operator_review_DRAFT.json` | Modello per l'operatore: **nessun gruppo pre-approvato** |
| `alpha11_unresolved.csv` | Inverter per cui non è possibile avanzare una proposta sicura |
| `alpha10_hierarchy_review.json` | Gerarchia di base; nessun parent confermato senza HITL |
| `alpha10_scope_counts.csv` | Quantità per CU e inverter, già presenti in Alpha10 |

Per aprire i report:

```powershell
explorer '.\reports\sap_alpha11\PV11'
Invoke-Item '.\reports\sap_alpha11\PV11\alpha11_parent_proposals.csv'
Invoke-Item '.\reports\sap_alpha11\PV11\alpha11_review_suggested_groups.csv'
```

## HITL: confermare SOLO quanto verificato sul PDF

L'elaborazione produce gruppi di *suggerimenti*, mai approvazioni automatiche. La CU19, per cui il PDF riporta un prefisso inverter incoerente (`I 1.1` anziché la CU19 attesa), viene tenuta fuori dal gruppo senza anomalie.

Dopo aver verificato **tutte le CU elencate in ciascun gruppo**, eseguire:

```powershell
.\conferma_parent_TR_INV.bat
```

Inserire `PV11`. Per ogni gruppo il programma stampa gli ID CU coinvolti. Digitare `CONFERMO` solo se il documento dimostra che la regola si applica a **tutte** quelle CU. Occorre anche un `evidence_ref` descrittivo. Il file viene scritto in:

`reports\sap_alpha11\PV11\alpha11_operator_review_APPROVED.json`

**Non viene sovrascritto** se già esiste: per correggere una review, cambiare nome al file esistente o crearne uno nuovo dopo controllo. Se un gruppo copre alcune CU ma non tutte, non approvarlo in blocco; modificare il JSON HITL per inserire esplicitamente soltanto le CU verificate.

Poi rieseguire:

```powershell
.\diagnostica_parent_TR_INV_PDF.bat
```

Questa volta inserire anche il percorso completo del JSON `APPROVED`. Le associazioni effettivamente confermate vengono registrate nella gerarchia di base (`alpha10_hierarchy_review.json`) con `parentage=OPERATOR_CONFIRMED_TR_PARENT`. I suggerimenti già confermati non vengono riproposti.

### Esempio documentato su CU2

Per una prova limitata alla sola **CU2**, con due relazioni TR e quattro inverter già verificati nel dettaglio discusso con l'operatore, si può utilizzare il file:

`examples\ALPHA11_PV11_CU2_REVIEW_EXAMPLE.json`

**Non equivale alla conferma delle altre 21 CU.** Dopo l'applicazione, 4 inverter risultano confermati e 84 rimangono da verificare; la continuità elettrica non è comunque dimostrata dal software.

## Confronto indipendente con TXT

Soltanto *dopo* aver generato il report da PDF si può misurare il confronto con il TXT di Ground Truth:

```powershell
python -m sld_ci_v04_beta3.sap_parent_reference_cli --proposals-json '.\reports\sap_alpha11\PV11\alpha11_parent_proposals.json' --reference-txt 'C:\percorso\Caratteristiche PV PP Pampa Norte.txt' --out '.\reports\sap_alpha11\PV11\parentage_comparison.csv'
```

Questo confronto non partecipa alla generazione delle proposte e non modifica gli output del motore.

## Risultati della verifica interna su Pampa Norte

- Etichette CU: **22**; TR candidati: **44**; inverter candidati: **88**.
- Associazioni geometriche TR → inverter proposte: **88 su 88**.
- Confronto indipendente dell'identita' del TR padre rispetto al TXT: **88/88 corrispondenze** (solo confronto dei padri; il vecchio TXT ha una discrepanza gia' corretta dall'operatore nelle quantita' SB della CU2, irrilevante a questo confronto).
- Suggerimenti HITL raggruppati: **3** (TR1 per 21 CU senza etichette conflittuali; TR1 per CU19 da verificare separatamente; TR2 per 22 CU).
- Appartenenze automaticamente confermate: **0**; percorsi elettrici verificati: **0**.
- Settimo Torinese, senza testo nativo: **0** proposte; resta da utilizzare l'HITL oppure introdurre in futuro il riconoscimento del testo grafico.

**Copertura effettiva:** questo primo riconoscitore si applica a una specifica organizzazione documentale e disposizione delle etichette (come il disegno Pampa Norte), non a qualunque SLD orientato o disegnato diversamente. Le conclusioni non devono essere generalizzate ad altri stili senza prova.

## Test e preservazione

- Suite `beta3`: **187 test**, inclusi 21 nuovi test Alpha11.
- Suite `dev14c` originale: **49 test**.
- Totale: **236/236 test superati** nell'ambiente di sviluppo, dopo verifica dei PDF sintetici fixture.
- I **76 file** di `sld_ci_v04_beta2_dev14c/` sono byte-per-byte invariati rispetto allo ZIP Alpha10.
- Non è stato modificato Alpha10; la nuova diagnostica è un comando separato.

## Non ancora realizzato

Non ci sono ancora: connessioni TR→INV dimostrate attraversando terminali e conduttori, riconoscimento generalizzato per il PDF Settimo senza testo, identificazione definitiva degli IOCB e trasformatori LV/LV, formato definitivo di import Matrix Flow e generazione delle Functional Locations SAP.
