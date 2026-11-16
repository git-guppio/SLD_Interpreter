# SLD2Hierarchy Beta3 / Alpha10 SAP-first — prima diagnostica documentale

**Scopo immediato:** riconoscere quantità e contesti CU / trasformatore / inverter centralizzati / String Box da un PDF SLD, mantenendo distinte le evidenze automatiche dalle conferme Human-in-the-Loop (HITL). **NON** genera Functional Locations SAP, **NON** importa direttamente in Matrix Flow, **NON** dimostra connettività elettrica.

## Baseline e vincoli

- Alpha9 SAP-FIRST è conservato; le nuove funzionalità sono in `sld_ci_v04_beta3/sap/label_first.py` e due CLI nuove.
- Il motore `sld_ci_v04_beta2_dev14c/` NON è modificato.
- Inverter di stringa e Bastardo sono esclusi dalla PoC. Non inferire un limite di due inverter per trasformatore; un TR puo' avere piu' inverter.
- L'associazione elettrica TR → inverter determina il parent SAP, **quando supportata da evidenza**. In assenza di tale evidenza il `parent_id` dell'inverter rimane nullo e il `cu_context_id` conserva solo l'appartenenza di contesto.
- F02 / F03 ecc. feeder sono fuori dal percorso critico SAP. Nessun device mancante viene creato per imporre minimi.
- Nessuna Ground Truth puo' entrare nel riconoscitore. I TXT forniti dall'operatore devono essere usati **solo in seguito** per valutazione indipendente, oppure come origine documentata di singole conferme HITL.

## Windows PowerShell

Estrarre ZIP in una cartella nuova (non sovrascrivere Alpha9). Aprire PowerShell dentro la directory:

```powershell
.\run_tests.bat
.\diagnostica_gerarchia_SAP_PDF.bat
```

Digitare il percorso completo di `PV11_Pampa_Norte.pdf` o `PV13_Settimo_Torinese.pdf`, l'identificativo `PV11`/`PV13` e lasciare vuoto il campo JSON HITL al primo passaggio.

I risultati sono salvati in `reports\sap_alpha10\<plant_id>\`:

- `alpha10_hierarchy_review.json`: evidenze, etichette, coordinate, genitori confermati o irrisolti;
- `alpha10_asset_candidates.csv`: elementi candidati e quantita' documentali (una voce da 10 String Box **non e' 10 dispositivi individualmente identificati**);
- `alpha10_scope_counts.csv`: conteggi per CU/inverter, con parent TR confermato o non risolto;
- `alpha10_review_tasks.csv` e `alpha10_review_groups.csv`: anomalie e fabbisogno HITL raggruppato;
- `alpha10_operator_review_TEMPLATE.json`: template vuoto per le conferme.

Aprire velocemente i report:

```powershell
explorer '.\reports\sap_alpha10\PV11'
Invoke-Item '.\reports\sap_alpha10\PV11\alpha10_scope_counts.csv'
Invoke-Item '.\reports\sap_alpha10\PV11\alpha10_review_groups.csv'
```

### HITL controllato per i parent TR/inverter

Copiare il template in un file **nuovo**, compilando `confirmed_tr_inverter_groups` soltanto dopo verifica manuale del diagramma. Schema esemplificativo (nessun dato reale di impianto):

```json
{
  "schema": "sld-sap-alpha10-reviewed-parentage/v1",
  "plant_id": "CI::ESEMPIO",
  "confirmed_tr_inverter_groups": [
    {"cu_ids": [1, 3], "transformer_slot": 1, "inverter_slots": [1, 2, 3],
     "evidence_ref": "SLD:pagina:coerenza schema tipico verificata manualmente per CU1 e CU3"}
  ],
  "confirmed_assets": []
}
```

La conferma e' limitata agli ID CU elencati. Nessuna generalizzazione automatica a tutto l'impianto. Il software rifiuta parent errati, TR assenti e ID duplicati. Il JSON di review non va modificato per impostare una quantita' soltanto *attesa* come se fosse verificata.

Per una pagina vettoriale priva di testo nativo (Settimo), si puo' usare `confirmed_assets` del template per registrare **uno per uno** dispositivi/quantita' espressamente verificati dall'operatore. Ogni asset deve avere un `asset_id` univoco sotto `CI::<plant_id>`, `type`, `parent_id` (o `cu_context_id` per inverter senza TR identificato), `evidence_ref`; solo `STRING_BOX_QUANTITY` ammette `quantity > 1`. Il modulo non compila questi dati automaticamente dal TXT.

Per ripetere l'analisi con conferme, rilanciare la diagnostica e indicare il percorso del JSON compilato nella terza domanda. La review non modifica il PDF né Alpha9.

### Confronto Ground Truth post-inferenza (Pampa Norte)

Completare **prima** il riconoscimento PDF, poi eseguire separatamente:

```powershell
python -m sld_ci_v04_beta3.sap_reference_cli --report '.\reports\sap_alpha10\PV11\alpha10_hierarchy_review.json' --reference-txt 'C:\...\Caratteristiche PV PP Pampa Norte.txt' --out '.\reports\sap_alpha10\PV11\alpha10_independent_comparison.csv'
```

Il comando e' un valutatore indipendente, non viene mai importato dal motore di inferenza.

## Verifica locale svolta

- **PV11 Pampa Norte:** 22 etichette CU, 44 etichette TR (candidati), 88 inverter (uno con ID testuale incoerente presso CU19), 88 quantita' String Box abbinate ai rispettivi inverter; somma documentale 923. L'inferenza non ha ricevuto alcun TXT.
- **Verifica *separata* contro TXT:** 86/88 quantita' SB per inverter coincidono. Per CU2 il PDF indica 10/11 (INV3/INV4) e il TXT 11/10. Da verificare quale riferimento sia corretto; la macchina non modifica il PDF per aderire al TXT.
- **PV13 Settimo Torinese:** foglio vettoriale con zero parole native estraibili; questa prima diagnostica **non** identifica autonomamente CU e inverter. Richiesto OCR adeguato o HITL. In particolare, il fatto che il TXT elenchi 3 inverter non autorizza il motore a produrre 3 inverter riconosciuti automaticamente.

### Limiti tecnici

- La ricerca di CU, TR, inverter e String Box usa etichette native e associazioni geometriche locali; la resa puo' cambiare molto con rotazioni e stili CAD diversi.
- Le 44 etichette TR del PV11 non bastano a dimostrare le singole connessioni TR/inverter. Per questo il parent di ciascun inverter rimane da confermare.
- Il totale 923 e' la **somma delle quantita' documentali**, non 923 simboli SB individuati e verificati singolarmente.
- La nomenclatura di IOCB e LV/LV e' ancora da cercare/verificare sui documenti: non viene assegnata automaticamente.
- Resta da verificare il tracciato reale del Matrix Flow. Nessuna FL viene generata.
