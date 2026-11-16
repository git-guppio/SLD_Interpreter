# SLD2Hierarchy — Stato verificato Alpha 22

**Perimetro:** PV con inverter centralizzati. Obiettivo: alberatura SAP
utilizzabile da Matrix FLOW. Non comprende BESS, wind o PV string inverter.

| Caso | Asset da documento | Parent TR-INVERTER | Output |
|---|---|---|---|
| Pampa Norte PV11 | 22 CU, 44 TR candidati, 88 INV, 923 SB | Candidati; i conteggi SB sono stati verificati per inverter | Excel/CSV |
| PV6 | 2 CU, 3 TR candidati, 3 INV, 35 SB | Candidati non verificati indipendentemente | Excel/CSV |
| PV8 | 55 CU, 110 TR candidati, 220 INV, 1.320 SB | Candidati non verificati elettricamente | Excel/CSV |
| Settimo PV13 | 3 inverter candidati e 24 QPS (8 ciascuno), TR simile per simbolo | 1 CU, 1 TR, 3 INV **confermati dall'operatore**, bus CAD e 4 gap con motivi di apparecchiatura candidati, non attraversati | Excel/CSV con review, audit CAD |
| PV3 | 3 inverter candidati, 24 QPS documentati, bus CAD | Nessuna review del PDF e nessuna promozione a TR verificato | Solo diagnostica |

Per Settimo le discontinuità sono **una TR-secondario→sbarra e tre
sbarra→ingressi inverter**. Il programma NON le salta automaticamente.

## Cosa è realmente migliorato da Alpha 21

Prima Alpha21 poteva proporre un unico TR in prossimità dei tre morsetti, ma
mancava una sbarra comune esplicita. Ora Alpha22 documenta:

1. indice e coordinate della sbarra sorgente del PDF;
2. tre rami inverter tracciati e relative discontinuità;
3. indice e coordinate del tratto secondario del TR candidato;
4. stati di astensione per sbarre, avvolgimenti e terminali ambigui;
5. quattro motivi di apparecchiatura verde/magenta rilevati negli stessi gap (classificazione ancora aperta);
6. dettaglio visivo ingrandito per il controllo HITL.

**I collegamenti automatici TR→INV completi restano 0 su Settimo**:
la qualità del risultato è la maggiore prova documentale, NON una parentela
SAP automaticamente certificata.

## Blocchi per il prodotto finale

1. Riconoscere e attraversare come **archi di apparecchiatura** (non ponti di
   conduttore) gli interruttori e i componenti realmente in serie; distinguere
   dispositivi aperti/chiusi, simboli di misura e collegamenti ausiliari.
2. Identificare IOCB, TR LV/LV e loro genitori senza crearli dai minimi SAP attesi.
3. Misurare precision, recall e accuratezza Parent/Child su un corpus nuovo
   non usato per sviluppare alcuna regola; non contare come indipendenti i
   documenti geometricamente quasi duplicati.
4. Verificare uno schema di import Matrix FLOW concordato con il responsabile
   dell'interfaccia e un caricamento end-to-end di prova.

Non dichiarare un SLD generico riconosciuto solo perché i test del codice
passano: 384/384 è regressione software, **non** precisione sul mondo reale.
