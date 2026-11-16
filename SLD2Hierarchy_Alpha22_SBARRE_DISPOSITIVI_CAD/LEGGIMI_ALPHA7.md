# SLD2Hierarchy beta3 — Integrated Alpha 7

**Obiettivo:** proporre l'associazione fra un'etichetta, un possibile simbolo vettoriale e punti di contatto grafici, lasciando esplicita la distanza fra un candidato e un collegamento elettrico dimostrato. Esempi reali: PV5, PV6, PV7; controllo negativo su richiami/documentazione PV4.

## Esecuzione Windows (PowerShell)

1. Estrarre lo ZIP Alpha 7 in una cartella nuova, senza sovrascrivere Alpha 6.
2. Per la regressione, aprire PowerShell nella cartella Alpha 7 ed eseguire ` .\run_tests.bat ` (i file BAT sono eseguibili direttamente da PowerShell).
3. Per la nuova diagnostica, eseguire ` .\diagnostica_simboli_terminali_PDF.bat `. Indicare **percorso completo con `.pdf`**, impianto facoltativo e numero di pagine da approfondire (INVIO = 3).
4. Report: `reports\alpha7_symbol_review.json` e `reports\alpha7_symbol_review.csv`. I CSV servono per la revisione tecnica, non per il funzionamento del programma.
5. La diagnostica multistile preesistente (`.\diagnostica_multistile_PDF.bat`) continua a funzionare e include i dati Alpha 7 nel suo JSON.

Per il PV4 dell'utente, riutilizzare il percorso *di cinque pagine* già usato per Alpha 6: `...\data\CASE_004_PV4\input\PV4_SLD.pdf`. **Non confondere** questo documento con il PDF `PV4.pdf` del corpus, composto da 71 pagine. Le analisi sul secondo non certificano il risultato sul primo.

## Novità

- Analisi **locale**, utilizzando le regioni ROI già selezionate da Alpha 6 anche per pagine dense.
- Rilevatore preliminare di **due anelli di Bézier allineati**, di dimensioni simili, vicini a un tag classificato come trasformatore. Le forme possono essere altro: la dicitura nel JSON è sempre `SINGLE_PAIRED_CIRCLE_SYMBOL_CANDIDATE`, **non** un asset verificato.
- Ipotesi dei **punti geometrici di contatto**: estremi di segmenti solidi, prossimi al perimetro di uno degli anelli e con segmento in uscita dal corpo. Gli elementi tratteggiati non vengono promossi a contatti. Non sono terminali fisici certificati né prove di continuità.
- Collisioni: se lo stesso paio di cerchi risulta candidato per più tag selezionati, entrambi i casi passano a `SAME_SYMBOL_CANDIDATE_FOR_MULTIPLE_TAGS`, senza scelta arbitraria o doppio conteggio del simbolo.
- I riferimenti del tipo `SEE SHEET`, `DETAIL`, `FIELD MET STATION` in vicinanza ai tag sono registrati come **contesto documentale** da revisionare; non generano asset.
- La selezione delle pagine nel campione geometrico privilegia quelle con etichette di tipo trasformatore supportate dal rilevatore. Tutti i limiti di campionamento continuano a essere indicati.
- Tracciabilità: pagina, bbox, ID dei due disegni a cerchio, ID segmento e coordinate del punto candidato.
- Coda di revisione strutturata: `alpha7_symbol_review_queue` nel report multistile e report autonomo in JSON/CSV.

## Limiti non risolti (non dichiarare risultati inesistenti)

- Riconoscimento di celle MT, inverter, interruttori, trasformatori a simbologia differente da due cerchi: **ancora incompleto**.
- Il confronto fra tag e forma, anche quando unico, **non prova** che i cerchi siano un trasformatore o una particolare istanza di asset fisico.
- I contatti con il simbolo **non sono terminali verificati**; non attraversare o collegare automaticamente dispositivi elettrici.
- Nessun feeder–CU verificato, nessuna continuità elettrica tra fogli o attraverso dispositivi aggiunta da Alpha 7. I conteggi di veri asset restano `null` dove non dimostrati.
- I risultati reali sono campionati e non possono fornire precisione/richiamo dei dispositivi senza annotazioni indipendenti.
- Sono supportati PDF vettoriali con testo nativo. L'OCR resta un'attività separata.

## Prove interne

- 8 test nuovi di nonregressione e di sicurezza sulle ipotesi di simboli/contatti. 114 test beta3 di Alpha 6 preservati, oltre ai 49 test del dev14c originale invariato (totale **171 test**).
- PV5/6/7: rinvenuti simboli circolari e contatti **candidati** con coordinate sorgente.
- PV4 originale, 71 pagine: le etichette `XFR` trovate su tavole con richiami a `FIELD MET STATION` non sono state convertite in dispositivi né in collegamenti elettrici verificati.

## Fase successiva

Per assegnare terminali fisici verificati servono un vocabolario di simboli per categorie, discriminanti di tipo di foglio, collegamenti vettoriali senza salti, trattamento di interruttori e sezionatori, e una revisione indipendente di un sottoinsieme per costruire il benchmark. Solo dopo queste verifiche è legittimo alimentare il grafo feeder–CU.
