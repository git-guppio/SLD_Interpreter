# SLD2Hierarchy – Roadmap verso la versione operativa

**Obiettivo**: da un SLD fotovoltaico con inverter centralizzati, estrarre una
gerarchia affidabile `CU | TR | INV | STR_Box` e le categorie SAP richieste;
trasmetterle a Matrix FLOW solo dopo convalida e verifica dell'interfaccia.
Nessun inverter stringa o architettura BESS nel perimetro di questa PoC.

## Dove siamo realmente

| Fonte | Capacita' dimostrata | Limite aperto |
| --- | --- | --- |
| PV11 Pampa Norte | 22 CU; 88 inverter; 923 SB complessive, 88/88 quantita' per inverter confrontate e corrette | Parent TR-inverter proposti, non verificati per continuita' elettrica |
| PV5 / PV6 / PV7 | Seconda famiglia di identificativi e conteggi indicizzati, alcune sequenze incomplete | Validazione indipendente puntuale e generalizzazione |
| PV8 | 55 sottocampi, 220 INV, 1320 SB derivati da ID individuali | Parent TR proposti e generalizzazione a disegni multipagina non omogenei |
| Settimo + PV3 | 3 simboli di conversione candidati per disegno; 3 campi grafici con 8 compartimenti ciascuno; associazioni solo per ordine | No conteggio SB dimostrabile; TR/CU non ancora classificati. Quasi duplicati, non 2 validazioni indipendenti |

I numeri in tabella hanno **livelli di validazione differenti**; non usarli
come prova di accuratezza generale. Gli autotest software non sono una metrica
di accuratezza del riconoscitore.

## Passi tecnici in ordine prioritario

1. **Catalogo dei dati e test di regressione indipendente**. Separare gli SLD
   di sviluppo dagli SLD *held-out*; predisporre annotazioni per ogni apparecchiatura
   (bbox, tipo, parent, quantita' SB, pagina, fonte). La GT NON entra nel motore.
2. **Interpretazione CAD senza testo**. Isolare simboli di TR, inverter e String Box
   per topologia e caratteristiche geometriche; espandere il riconoscimento
   dalle etichette ai simboli anche con colori arbitrari. OCR offline solo
   dove serve. Non equiparare forme ripetute a dispositivi per default.
3. **Ricostruzione della connettivita' e gerarchia**. Riconciliare conduttori,
   interruttori e simboli attraverso pagine, orientamenti e fogli di dettaglio;
   mantenere grado `1..N` per inverter per trasformatore, senza limiti artificiali.
4. **Controlli qualita' per singola riga**. Marcare `observed / inferred /
   operator_confirmed / unresolved`; dare priorita' alle revisioni che incidono
   sull'output `CU|TR|INV|STR_Box`. Nessuna cifra inventata.
5. **Contratto Matrix FLOW**. Concordare campi, codifiche SAP, sistema di
   numerazione e validazione CSV/XLSX; eseguire una prova reale di import su
   un impianto con gerarchia confermata.
6. **Valutazione fuori campione**. Misurare precision, recall e correttezza
   parent per tipologia, impianto e stile, insieme a numero/tempo di interventi
   HITL; definire soglie di accettazione con l'owner prima della release.

## Criteri di uscita per il prodotto

- Nessuna CU, TR, INV o String Box inventata per soddisfare minimi di business;
- ogni collegamento parent e ogni conteggio SB ha una fonte riproducibile;
- errori misurati su documenti non usati per definire le regole;
- se una tipologia PDF non e' supportata, output esplicito `NON RISOLTO`, non
  un Excel apparentemente completo ma sbagliato;
- tracciato Matrix FLOW convalidato da un test di caricamento effettivo.

## Limitazione della milestone Alpha19

La nuova funzione associa soltanto *motivi grafici ordinati*. Non e' un passo
sufficiente da solo a validare le 16 String Box per inverter di Settimo;
questa informazione va dedotta da simboli/annotazioni inequivocabili o
confermata da un operatore. I file TXT restano riferimenti di verifica, non
input del riconoscimento.
