# Alpha 20 – Tracciamento di conduttori CAD fino ai morsetti

## Novità tecnica

Alpha 20 **non sostituisce** il riconoscimento esistente. Aggiunge al percorso CAD
senza testo nativo un controllo dei tratti di conduttore **solidi e neri** che
raggiungono l'ingresso dei moduli di conversione candidati.

Prima (Alpha 19): una corrispondenza inverter/campo era proposta soltanto
per ordine di posizione. Ora si distingue anche un'evidenza indipendente:
la **continuità geometrica di una traccia di conduttore in ingresso** fino
al primo morsetto aperto a monte. Tratti interrotti, incroci privi di
estremità in comune e linee tratteggiate non vengono attraversati.

Questo è un risultato di geometria delle linee, **non** una prova che un
trasformatore sia il padre: un contatto/interruttore nel circuito interrompe
il percorso e deve essere interpretato da un modulo successivo o verificato.

## Comandi

Interfaccia unica: `AVVIA_SLD2HIERARCHY.bat`.

Diagnostica diretta:

```powershell
python -m sld_ci_v04_beta3.alpha20_cli --pdf "C:\\dati\\schema.pdf" --out "reports\\cad_alpha20"
```

Risultati generati:

- `alpha20_morsetti_ingresso.csv`: per ogni modulo candidato il numero dei
  segmenti continui e il morsetto aperto da verificare;
- `alpha20_conduttori_ingresso.json`: coordinate di ogni tratto originale,
  provenienza e classificazione; comprende gli identificativi degli inverter;
- `alpha20_tracce_ingresso_p1.png`: immagine con le tracce continue evidenziate;
- `alpha20_cabinet_candidati.csv`: conteggi e test geometrici dei 24 cabinet;
- `alpha20_qps_documentali.csv`: sequenze QPS da OCR locale singolo, quando disponibile;
- `alpha20_tr_simboli_vettoriali.csv`: coppie di avvolgimenti candidate;
- `alpha20_cabinet_dc_p1.png`: candidate cabinet evidenziate;
- vengono mantenuti i report precedenti Alpha18/19.

**OCR facoltativo:** sul computer deve essere presente Tesseract OCR offline
(eseguibile nel PATH o in `C:\Program Files\Tesseract-OCR`). Non e' incluso
nel ZIP. Se non e' disponibile, l'analisi dei conduttori e dei simboli procede
comunque, e i dati QPS OCR rimangono `OCR_NOT_AVAILABLE`. Il programma non fa
richieste di rete e non legge i file TXT di Ground Truth.

## Risultato sui due CAD disponibili

Settimo Torinese e PV3 producono entrambi tre moduli candidati, tre tracce di
ingresso rilevate e tre morsetti a monte sulla stessa quota.
Per i tre moduli la diagnostica rileva rispettivamente 3, 1 e 3 tratti
contigui dal modulo fino al morsetto aperto.

Inoltre si riconoscono per geometria 24 cabinet DC-like (8 per campo):
ogni compartimento presenta la sbarra DC rossa e il simbolo verde di protezione.
Un **unico OCR locale** applicato alla zona dei cabinet recupera 24 ID
numerati `QPS-1-1/8..8/8`, `QPS-2-1/8..8/8`, `QPS-3-1/8..8/8`,
ricostruendo la sequenza completa in modo indipendente dalla geometria.
I prefissi letti tramite OCR (ad es. `OPS`, `aPS` anziche `QPS`) vengono
conservati nei dati grezzi e normalizzati solo come ipotesi verificabile.

Anche il simbolo vettoriale di una **coppia di avvolgimenti circolari** e'
stato identificato sul medesimo asse dei morsetti a monte: e' un candidato
al trasformatore principale, ma NON un legame elettrico dimostrato.

Il padre TR, la CU e il numero di **String Box SAP** non sono ancora
determinati automaticamente. Il PDF presenta otto QPS per campo, mentre
il documento Ground Truth fornito separatamente riporta 16 SB/inverter:
non tradurre QPS in String Box senza stabilire la corrispondenza semantica.

I due disegni sono quasi duplicati: non costituiscono due validazioni
indipendenti su un nuovo stile.

## Sicurezza e compatibilità

- PDF originale sempre letto in sola lettura;
- nessun riferimento alle Ground Truth e nessun invio a servizi esterni;
- niente ponti automatici su incroci, aperture, apparecchi o distanze:
  al dubbio viene segnalato un percorso incompleto;
- nessuna regola rigida sul numero inverter per TR;
- solo inverter centralizzati PV nel perimetro di questa PoC;
- le funzioni precedenti e l'export `CU|TR|INV|STR_Box` per gli SLD supportati
  rimangono invariati.

## Cosa NON è ancora risolto

1. Identificare e verificare il trasformatore (con simboli e dati di targa)
   e il collegamento **attraverso** dispositivi di manovra fino agli inverter.
2. Classificare le singole String Box dai blocchi CAD a valle e collegarle
   per conduttore. Otto compartimenti grafici non provano né otto né sedici SB.
3. Estendere la topologia a simboli e stili diversi, con validazione indipendente.
4. Verificare il tracciato effettivo di import con Matrix FLOW.

**Nessun numero non accertato viene presentato come pronto per l'import SAP.**

Per lo stato complessivo e le attività necessarie al prodotto, leggere `STATO_PRODOTTO_ALPHA20.md`.
