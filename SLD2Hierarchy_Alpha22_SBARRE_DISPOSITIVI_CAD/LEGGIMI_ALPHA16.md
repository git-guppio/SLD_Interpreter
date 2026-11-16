# SLD2Hierarchy — Alpha 16 / terza famiglia documentale (PV8)

## Scopo

Alpha 16 aggiunge al workbench un **terzo riconoscitore documentale** per SLD fotovoltaici con inverter centralizzati. Il codice resta **Python**; il file `.bat` avvia l'interfaccia Windows.

L'incremento non cambia i motori Alpha 12 (Pampa Norte) né Alpha 15 (tag TPO/INV/CST di PV5-7). Seleziona automaticamente il percorso in base alle evidenze del PDF, **non al nome dell'impianto**.

## Avvio

1. Estrarre lo ZIP in una cartella separata, senza sostituire le versioni precedenti.
2. Eseguire `AVVIA_SLD2HIERARCHY.bat` (doppio clic, oppure da PowerShell ` .\AVVIA_SLD2HIERARCHY.bat `).
3. Cliccare su **1 Analizza SLD**, scegliere `PV8.pdf` nella finestra Windows, confermare l'identificativo dell'impianto.
4. I risultati vengono scritti sotto `reports\sap_alpha16\<ID>\<data_ora>` senza sovrascrittura.
5. Aprire `alpha16_gerarchie_stereotipi.xlsx`, oppure il CSV a quattro colonne.

Per eseguire il solo metodo Alpha16 da CLI:

```powershell
python -m sld_ci_v04_beta3.alpha16_cli --pdf "C:\percorso\PV8.pdf" --plant-id PV8 --out "reports\test_PV8"
```

## Come funziona il terzo riconoscitore

- Identifica **inverter reali** da etichette autonome `Inv.<CU>.<INV>` (non dalle loro occorrenze nei nomi dei cavi).
- Identifica la singola String Box tramite `LVL-SB.<CU>.<INV>.<seriale>-INV.<CU>.<INV>`; il collegamento **box -> inverter** è dichiarato nel testo stesso della sorgente.
- Deduplica gli identificativi; conta il totale per inverter **solo se la sequenza di seriali è completa** `1..N`. Se mancano seriali, lascia `STR_Box` vuoto e produce un'anomalia. `String ... .20` sono stringhe per box e **non** il numero delle String Box.
- Identifica **trasformatori candidati** mediante due etichette vicine: potenza kVA e rapporto tensione. Non assume un numero predefinito di TR o inverter.
- Propone l'associazione `TR -> INV` sulla posizione orizzontale delle etichette; se l'assegnazione è ambigua, la lascia non risolta. Il progressivo TR è assegnato da sinistra a destra **per ciascun disegno**, perché lo SLD PV8 non espone un numero TR esplicito; non va interpretato come tag originale.
- Il passaggio `Subcampo -> CU` è una convenzione semantica **da verificare con il responsabile degli asset** prima dell'import in SAP.
- Non determina la continuità elettrica dei conduttori; ogni associazione TR–INV resta `CANDIDATO_PER_PROSSIMITA_X_NON_ELETTRICO`.

## Risultato ottenuto sul documento PV8 caricato

| Voce | Quantità documentale |
|---|---:|
| Pagine PDF | 56 (1 overview + 55 schemi di subcampo) |
| Sottocampi/CU | 55 |
| Trasformatori candidati da rating + rapporto tensione | 110 |
| Inverter con etichetta autonoma | 220 |
| Inverter con sequenza di box completa | 220/220 |
| Box identificate individualmente | 1.320 |
| Proposte di padre TR per inverter | 220 |
| Connessioni elettriche verificate dal software | **0** |

Nessuna Ground Truth è stata immessa nel riconoscitore. L'output è **staging per validazione**, non un tracciato Matrix Flow certificato. La corrispondenza quantitativa **non** dimostra la correttezza dei parent.

## File prodotti dal terzo metodo

- `alpha16_CU_TR_INV_STR_Box.csv` — un inverter per riga, numerazione inverter che riparte da 1 a ogni TR, quattro colonne;
- `alpha16_gerarchie_stereotipi.xlsx` — Dettaglio, Riepilogo, Controlli CU, Evidenze;
- `alpha16_evidenze.csv` — per ogni inverter: etichette, pagina, posizioni, motivo della proposta;
- `alpha16_diagnostica.json` — tutte le entità, anomalie e informazioni di provenienza.

Il colore verde corrisponde alla *cardinalità prevalente nell'impianto*, non a un collegamento elettrico verificato. Le quantità SB sono sempre conteggi di identificativi espliciti, non moltiplicazioni di capacità teoriche.

## Risultati sulle altre famiglie

- **PV11 Pampa Norte** → percorso Alpha 12 invariato (88 INV / 923 SB, quantità per inverter validate sul documento con supporto manuale).
- **PV5, PV6, PV7** → percorso Alpha 15 invariato (tag TPO/INV/CST), ancora da validare indipendentemente sulle gerarchie.
- **PV8** → terzo percorso Alpha 16 (LVL-SB / INV).
- **PV3, PV13** → nessun nuovo riconoscimento: resta necessario un modulo grafico/OCR.

Il visualizzatore di evidenze Alpha 13 lavora ancora solo sui report Alpha 12; per Alpha 15/16 si usano per ora le evidenze CSV/Excel/PDF. Le correzioni per PV8 non devono essere caricate attraverso la vecchia funzione HITL Alpha 13.

## Test

`run_tests.bat` — suite complessiva attesa **302/302** (253 beta3 inclusi 11 Alpha16, più 49 dev14c). Nel nuovo modulo sono inclusi test contro: fanout limitato, seriali box mancanti, etichette con scope incoerente, TR senza rapporto tensione, CU multiple sulla stessa pagina, geometria ambigua, PDF senza asset, validità output, prova sullo scope del progetto.

## Presentazione al responsabile

Traguardo oggettivo: **tre convenzioni documentali distinte** interpretate da un'unica interfaccia, con un caso validato puntualmente (PV11), due altri gruppi che forniscono extraction staging e tracciabilità, e limiti ancora aperti su SLD raster/no-native-text, generalizzazione cross-plant, e verifica dei parent elettrici. Non dichiarare una percentuale di precisione senza un benchmark indipendente.
