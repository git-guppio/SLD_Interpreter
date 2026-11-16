# SLD Interpreter – requisiti della PoC SAP (congelati il 16/10/2026)

Questo documento conserva le decisioni prese DOPO il report di avanzamento
pubblicato su Teams. È il contratto funzionale di Alpha 9 e successive, fino a
nuove indicazioni esplicite. Non rappresenta una validazione elettrica generale
né una norma universale per gli impianti fotovoltaici.

## Scopo e confini

**Obiettivo prioritario:** SLD e layout eventuale → asset riconosciuti →
appartenenze gerarchiche → interventi HITL indispensabili → output di STAGING
per Matrix Flow → generazione delle Functional Locations SAP in una fase
successiva, quando lo schema di import Matrix Flow sarà disponibile.

**Fuori dal percorso critico:** verifica del grafo elettrico completo,
tracciamento feeder–CU, IEC 60617 estesa a tutti i dispositivi, riconoscimento
di elementi intermedi non richiesti per la gerarchia SAP. Le componenti
esistenti non si eliminano: si mantengono per applicazioni future.

## Gerarchia vincolante della PoC: FV a inverter centralizzati

- Per ogni impianto: almeno **1 Conversion Unit (CU)**.
- Per ogni CU: almeno **1 Inverter Output Circuit Breaker (IOCB)**,
  almeno **1 trasformatore elevatore LV/MV**, almeno **1 inverter centralizzato**.
- Per ogni inverter: almeno **1 trasformatore LV/LV di campo** e
  almeno **1 String Box** (come requisito SAP concordato).
- Non ci sono limiti massimi imposti. Non va imposto un rapporto 1:1 o 1:2
  tra trasformatori LV/MV e inverter. Nella stessa CU sono ammesse
  configurazioni miste: TR con un secondario/1 inverter oppure TR con due
  secondari/2 inverter. Il TR con due secondari è SEMPRE 1 solo TR.
- Il feeder è un'informazione tecnica opzionale per la PoC SAP: nessun
  blocco della generazione gerarchica per CU–feeder non determinato.
- Gerarchia SAP: CU contiene IOCB, TR LV/MV e inverter; inverter contiene
  TR LV/LV e String Box. L'associazione elettrica TR LV/MV ↔ inverter è
  separata dal parent SAP dei nodi.

## Attendibilità, assenze e intervento umano

- Ogni asset deve avere identità stabile e parent risolto. Un minimo non
  dimostrato è una **verifica da richiedere**, mai un conteggio automatico pari a 1.
- Se lo SLD omette una categoria, il programma non ne deduce l'assenza
  fisica. Confrontare fonte documentale, geometria e conferme esplicite.
- HITL unicamente quando serve per cardinalità, identità o parent della
  gerarchia SAP. Preferire verifiche raggruppate per evitare richieste ripetitive.
- Registrare provenienza, confidenza e ambito dell'approvazione: nessuna
  applicazione automatica globale di regole confermate su un singolo impianto.
- Utilizzare IEC 60617 e OCR mirato per le sole sei categorie necessarie,
  e solo dove le fonti convenzionali non permettono il risultato SAP.

## Valutazione e nuova documentazione

- L'utente preparerà SLD migliori e inventari preliminari per le sei categorie,
  includendo quantità reali, quantità rappresentate, pagina e appartenenze.
- Ground Truth riservata al confronto; non usare quantità attese per forzare
  l'inferenza. Separare dati per sviluppo e per validazione indipendente.
- Il tracciato reale di Matrix Flow non è ancora stato mappato: qualsiasi CSV
  Alpha 9 è INTERMEDIO e non prova l'import SAP né genera Functional Locations.

## Baseline

- `SLD2Hierarchy_beta3_integrated_alpha8_2026-10-16_TEST_FIX.zip` è
  congelata e deve restare riproducibile. Suite verificata su Windows: 182/182.
- Il codice `sld_ci_v04_beta2_dev14c` è frozen; Alpha 9 aggiunge adapter e test
  nella parte beta3. Ogni rilascio deve superare i test vecchi e nuovi.

### Template documentale per l'operatore

Usare facoltativamente `examples/SAP_GROUND_TRUTH_TEMPLATE.csv`:
`quantity_known` e `quantity_graphically_drawn` sono DISTINTE. Lasciare
vuoto il valore sconosciuto: non usare 0 per assenza di evidenza. Indicare
pagina e note se una quantità è nota da altre fonti ma non è disegnata.
Il template è SOLO materiale di validazione, NON letto dal motore per guidare
l'inferenza. Nella PoC definitiva si dovrà inoltre descrivere l'identità
individuale degli asset quando sono presenti più unità dello stesso tipo.
