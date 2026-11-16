# SLD2Hierarchy Alpha 22 — Sbarre CAD e discontinuità documentate

## Perché serve

Nei CAD senza testo nativo, Alpha 21 riconosce tre moduli inverter, una
coppia di avvolgimenti candidata a TR, le sequenze QPS e i singoli tratti
continui dei conduttori. Non collega però i tratti interrotti dagli apparecchi.

Alpha 22 introduce un **audit della sbarra condivisa** basato sui segmenti
vettoriali originali. È un passo verso la verifica automatica delle
appartenenze TR→INV, ma **non chiude da solo le discontinuità elettriche**.

## Evidenza ricostruita sul CAD di Settimo

- una sbarra nera orizzontale, identificata dal segmento sorgente numero **94**
  (coordinate nel sistema normalizzato: x=485,269..531,881; y=242,373);
- tre ingressi inverter, ognuno tracciabile con i propri segmenti neri
  fino a un terminale aperto allineato alla sbarra;
- una coppia circolare di avvolgimenti candidata al trasformatore,
  con un tratto verticale sorgente numero **88** verso la sbarra;
- discontinuità tra il secondario del trasformatore e la sbarra, e tra la
  sbarra e i terminali dei tre inverter: **NON attraversate automaticamente**;
- la gerarchia Settimo `1 CU / 1 TR / 3 INV / 8 SB ciascuno` è riprodotta,
  ma le appartenenze del TR restano **confermate dall'operatore**, non
  dimostrate da un percorso elettrico automatico completo.

Gli indici 88/94 sono esempi della versione PDF verificata e non costituiscono
modelli da usare su altri disegni. Il programma li ricerca nuovamente ogni volta.

## Come avviare

Interfaccia con selettore Windows: `AVVIA_SLD2HIERARCHY.bat`.

Per il CAD di Settimo selezionare `PV13_Settimo_Torinese.pdf` e, se si desidera
l'Excel completo, il JSON specifico del PDF:
`examples/SETTIMO_TOP_SCHEMA_CONFERMATO_OPERATORE.json`.

Il file è verificato con **plant ID + SHA256 del PDF**. Non applicarlo a PV3
anche quando i disegni appaiono simili.

Il medesimo comando già usato con Alpha21 continua a funzionare; Alpha22
aggiunge i report, senza alterare il CSV `CU;TR;INV;STR_Box`:

```powershell
python -m sld_ci_v04_beta3.alpha22_cli --pdf "C:\SLD\schema.pdf" --plant-id IMPIANTO --out "reports\verifica"
```

Per i PDF CAD servono `PyMuPDF`, `Pillow`; per la lettura delle etichette QPS
serve anche **Tesseract OCR locale**. Nessuna API o trasferimento esterno.

## Nuovi output

- `alpha22_audit_sbarre_e_discontinuita.json`: sorgente PDF hash, segmenti
  del documento, eventuali sbarre ambigue, avvolgimenti candidati, gap;
- `alpha22_relazioni_candidati.csv`: una riga per ogni inverter agganciato
  come candidato alla sbarra; il TR rimane non verificato automaticamente;
- `alpha22_evidenze_sbarra_p1.png`: panoramica sul PDF originale;
- `alpha22_zoom_sbarra_p1.png`: dettaglio ingrandito delle discontinuità;
- tutti i report Alpha18–21 sono mantenuti, tra cui l'Excel a quattro colonne
  se la conferma dell'operatore è valida.

Colori nel dettaglio: **blu** = coppia avvolgimenti e tratto secondario;
**rosso** = sbarra vettoriale; **arancione** = terminali degli inverter e
spazi non attraversati; **viola** = simboli sorgente in serie ancora privi di
classificazione elettrica certa.

Con l'analisi dei tracciati colorati Alpha22 individua, su Settimo, **4
motivi grafici in serie**: uno nel tratto TR→sbarra, tre nei tratti
sbarra→inverter. Per ogni motivo conserva un indice di *path* sorgente
verde e gli indici dei tratti magenta contenuti. Questo è un insieme di
**candidati di apparecchiatura**, non il riconoscimento definitivo di
interruttore/IMS/TC né un attraversamento automatico del dispositivo.
Il CSV `alpha22_dispositivi_in_serie_candidati.csv` riporta le quattro
identificazioni e gli eventuali casi ambigui.

## Regole di sicurezza dell'inferenza

- Sbarra: esiste soltanto se un **segmento sorgente nero e continuo** copre
  tutti gli ingressi della pagina; almeno due ingressi sono necessari.
- Se due sbarre parallele sono indistinguibili, la ricerca **si astiene**.
- Un TR candidato richiede **sia** una coppia di avvolgimenti vettoriali
  **sia** un tratto sorgente in uscita dal suo asse e vicino alla sbarra.
- Non vengono inventati raccordi attraverso interruttori, trasformatori,
  relè, circuiti interrotti o incroci privi di evidenza.
- Nessun rapporto 1 TR:2 INV fisso: il modulo è stato verificato con 2, 3, 4
  e 7 inverter su una sbarra comune.
- Niente TXT Ground Truth, inventario o valori teorici come input.
- Il risultato NON è un tracciato di import certificato per Matrix FLOW.

## Stato della validazione

**384 test superati** (335 modulo integrato + 49 dev14c), di cui 17 nuovi.
Prove effettive con PDF originali: Settimo Torinese (con QPS/Excel verificati),
PV3 (diagnostica vettoriale senza review), PV11, PV6 e PV8 (regressione
numerica inalterata). PV3 è molto simile a Settimo e non è un test di stile
indipendente.

Verifiche end-to-end ancora aperte: riconoscimento automatico e attraversamento
semantico degli apparecchi di manovra/protezione; classificazione affidabile di
IOCB e LV/LV; validazione indipendente su stili nuovi; specifica e prova
dell'import reale Matrix FLOW. Vedere `STATO_PRODOTTO_ALPHA22.md`.
