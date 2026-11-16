# Stato tecnico prodotto SLD2Hierarchy (Alpha 21) — 11 novembre 2026

**Perimetro:** gerarchia SAP funzionale di SLD fotovoltaici con inverter centralizzati.

## Risolto rispetto ad Alpha 20

- Il costruttore/operator ha confermato che **QPS** significa **Quadro di Parallelo Stringhe**
  ed equivale a **String Box** per il disegno di Settimo.
- La sigla `QPS-2-4/8` identifica il quarto quadro dell'inverter 2,
  su otto quadri totali di quell'inverter (convenzione non universale).
- Sono stati individuati direttamente dal PDF **3 campi con 8 QPS ciascuno**, 24 in totale,
  con OCR locale e indipendente evidenza geometrica per la corrispondenza dei cabinet.
- La **topologia di Settimo** e' stata confermata dall'operatore: 1 CU, 1 TR,
  3 inverter centralizzati a valle del medesimo trasformatore, 8 SB per inverter.
- Il TXT originario che riportava 16 SB/inverter e' stato rettificato in un file separato;
  nessuno dei due TXT e' letto dal motore.
- Il motore produce ora CSV ed Excel a 4 colonne quando le relazioni CU/TR hanno una
  conferma esplicita, con traccia della provenienza di ogni valore.

## Rimane da risolvere prima di un prodotto SAP pronto per Matrix FLOW

- Tracciamento elettrico completo attraverso i dispositivi di manovra e protezione per
  identificare automaticamente il TR padre, indipendentemente dalla conferma operatore.
- Riconoscimento robusto degli SLD raster e CAD non classificabili secondo le convenzioni
  finora sviluppate; misurazione precision/recall su corpus indipendente.
- Altre categorie di apparecchiature necessarie per la gerarchia SAP (IOCB e LV/LV),
  solo se presenti e dimostrate nelle fonti: non creare asset dal minimo atteso.
- Tracciato d'import effettivo di Matrix FLOW e prova end-to-end con data owner.

## Nota sulle evidenze

- Numerosita QPS proviene dal PDF (non da dichiarazioni o inventari esterni).
- Significato QPS e rapporti CU–TR–INV confermati dall'operatore,
  **non** dalla continuita' elettrica automaticamente verificata.
- Nelle nuove tabelle non va usata la dicitura **STEREOTIPATO** sulla sola base di
  un'unica CU con un TR. Lo stereotipo richiede ripetizioni documentate tra scope.
- Uno schema differente puo' richiedere un nuovo significato delle sigle e una
  nuova regola di interpretazione dell'indice, senza trasferire 1/1/3/8 ad altri impianti.

## Regressione al 11/11/2026

Test: **367/367** (318 beta3 e 49 legacy dev14c); confronto documentale invariato:
Pampa Norte 22 CU / 44 TR candidati / 88 inverter / 923 SB;
PV5 7 CU / 13 TR candidati / 13 inverter (12/13 sequenze SB complete);
PV6 2 CU / 3 TR / 3 inverter; PV7 1 CU / 2 TR / 2 inverter;
PV8 55 CU / 110 TR candidati / 220 inverter / 1.320 SB.
Sono risultati delle rispettive convenzioni, non la prova che qualunque SLD
sia riconoscibile e non la prova elettrica di tutti i parent SAP.
