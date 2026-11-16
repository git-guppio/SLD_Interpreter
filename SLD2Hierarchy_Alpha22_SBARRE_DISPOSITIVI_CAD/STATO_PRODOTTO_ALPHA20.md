# SLD2Hierarchy — stato del prodotto dopo Alpha 20

**Ambito:** schemi unifilari di impianti fotovoltaici con **inverter centralizzati**. Non include impianti con string inverter, eolico o BESS. Il tracciato di esportazione richiesto è `CU | TR | INV | STR_Box`, una riga per inverter, con INV numerato da 1 per ogni trasformatore. Le quantità sono quelle **previste e rappresentate nello SLD**, non la capacità nominale del costruttore.

## Risultati riproducibili

| Documento | Capacità osservata | Validazione e limiti |
|---|---|---|
| PV11, Pampa Norte | 22 CU, 44 TR candidati, 88 inverter, 923 String Box | Le 88 quantità per inverter sono state confrontate con riferimento corretto; padre TR da geometria/HITL, non connettività elettrica dimostrata |
| PV5 | 13 inverter, 12/13 sequenze SB complete | Lettura di identificativi; un caso incompleto, nessuna precisione complessiva validata |
| PV6 | 3 inverter, 3/3 sequenze SB complete | Necessaria verifica indipendente della gerarchia |
| PV7 | 2 inverter, 1/2 sequenze SB complete | Un caso incompleto |
| PV8 | 55 sottocampi, 220 inverter, 1320 SB con identificativi singoli | Associazioni TR–INV ancora geometriche; da validare indipendentemente |
| PV13 Settimo / PV3 | 3 candidati conversione, 3 percorsi conduttori fino ai morsetti aperti, 24 cabinet DC-like, 24 identificativi QPS | Quasi duplicati: **una sola famiglia CAD**. Nessuna quantità `STR_Box` SAP certificata |

I conteggi riportano **evidenze estratte** o quantità confrontate, non autorizzano a dichiarare risolte tutte le gerarchie. I test unitari verificano regressione e gestione dei casi negativi; **non misurano recall/precision su documenti mai visti**.

## Limitazioni strutturali non ancora chiuse

1. **Semantica QPS / String Box.** Il disegno CAD contiene `QPS-g-1/8` ... `QPS-g-8/8`, per `g=1,2,3` (24 quadri). Il riferimento esterno riporta 16 String Box per inverter (48 complessive). Senza una definizione documentale autorevole non si può equiparare un QPS a una String Box né moltiplicare per 2. Il campo `STR_Box` per questi CAD resta vuoto. Da chiarire il significato dei due livelli, preferibilmente con legenda/censimento dell'impianto e un esempio di un quadro QPS.
2. **Continuità attraverso apparecchi elettrici.** Alpha 20 verifica tratti di filo a monte di ciascun convertitore **fino a morsetti aperti**, ma non attraversa automaticamente interruttori, protezioni, trasformatore e dispositivi non classificati. Occorre un grafo semantico a terminali verificabili.
3. **Tipo di trasformatore.** Una coppia di simboli di avvolgimento circolari è solo candidata. Non si può stabilire automaticamente, senza evidenze aggiuntive, che sia il preciso trasformatore LV/MV genitore di ciascun inverter.
4. **Generalizzazione.** Sono presenti almeno quattro convenzioni (Pampa, PV5/6/7, PV8, CAD Settimo/PV3). Servono SLD tenuti completamente fuori dallo sviluppo con gerarchie annotate, e benchmark di precision/recall anche per falsi positivi.
5. **Asset ancora mancanti:** IOCB e trasformatore LV/LV, previsti dalla gerarchia SAP concordata, richiedono riconoscimento ed evidenze proprie; l'assenza di riconoscimento non prova la loro assenza fisica.
6. **Matrix FLOW:** schema effettivo d'importazione non ancora documentato e provato end-to-end. L'Excel è uno staging; non è ancora un import SAP validato.

## Piano tecnico per il prodotto

**Prossima milestone A — Classificazione semantica CAD:** usare forma del simbolo, legenda, tensioni/rapporti e attributi locali per identificare transformer LV/MV, IOCB, central inverter, QPS, String Box; separare `observed`, `inferred`, `operator_confirmed`, `unresolved` con provenienza. La classificazione dei QPS va confrontata con il censimento reale senza usare quest'ultimo come input del riconoscitore.

**Milestone B — Grafo elettrico a terminali:** terminali dei dispositivi, conduttori con punti di giunzione, separazione incroci/T e tratteggio; continuità tramite apparecchi solo con regola di attraversamento per classe validata. Il numero di inverter per TR resta **1..N** senza massimo. Le ambiguità diventano ticket HITL localizzati.

**Milestone C — Benchmark indipendente:** audit per CU / TR / INV / String Box su stili diversi; confrontare identità, padre, quantità, falsi positivi e interventi HITL. Preservare il gruppo Pampa e i PDF già esplorati come regressione, senza chiamarli prova indipendente.

**Milestone D — Export operativo:** `CU | TR | INV | STR_Box`, stereo/eccezioni ed evidenze; import effettivo in Matrix FLOW con contratto di input confermato; **nessun dato irrisolto inserito come valore verificato**.

## Come riprodurre il nuovo controllo

Da cartella Alpha20: `AVVIA_SLD2HIERARCHY.bat`, oppure `DIAGNOSTICA_CAD_ALPHA20.bat`. Su un ambiente con Python e dipendenze installate:

```
python -m sld_ci_v04_beta3.alpha20_cli --pdf "C:\\percorso\\PV13_Settimo_Torinese.pdf" --out "reports\\cad_alpha20"
```

Tesseract OCR è **locale, facoltativo e non incluso** nello ZIP. Senza Tesseract i simboli e i conduttori sono analizzabili, ma i 24 identificativi QPS non vengono attestati mediante OCR. Il PDF non viene modificato. Per ora la diagnostica QPS OCR opera sulla prima pagina CAD con gli elementi grafici individuati; non è un OCR multipagina universale.

**La consegna Alpha20 non equivale al prodotto finale.** È un incremento misurabile verso il riconoscimento per evidenza, non un riconoscitore universale.
