# Alpha 18 — Identificazione strutturale di candidati di conversione nei CAD vettoriali

## Funzione introdotta

Nei PDF senza testo nativo (per esempio PV3 e Settimo) il motore identifica
**candidati grafici di moduli di conversione**, richiedendo tre indizi:

1. involucro/pannello grafico ciano;
2. simbolo diagonale di conversione, oppure corrispondenza con almeno due esempi
   simili individuati *nello stesso documento*;
3. sbarra rossa e partenze separate osservabili.

Rileva anche pannelli inferiori composti da compartimenti ripetuti. Non equipara
partenze, compartimenti o pannelli a String Box; non presume il numero di
inverter per TR; non assegna un parent TR senza verifica del collegamento.

**Questa NON è ancora una gerarchia SAP da Matrix FLOW.** I candidati sono
riferimenti grafici da validare; nessun asset è considerato verificato.

## Output

Per PDF senza testo nativo, l'avvio unico `AVVIA_SLD2HIERARCHY.bat` utilizza
la diagnostica Alpha 18 e produce:

- `alpha18_candidati_vettoriali.json`: risultati strutturati, evidenze,
  coordinate e stati di verifica;
- `alpha18_candidati_inverter.csv`: un record per candidato con numero delle
  partenze fisicamente osservate;
- `alpha18_compartimenti_grafici.csv`: pannelli e numero di compartimenti;
- `alpha18_campi_grafici.csv`: raggruppamenti di pannelli, senza dichiarare
  collegamento elettrico ad un inverter;
- `alpha18_anteprima_simboli_p1.png`: evidenze su un ritaglio della pagina.

Si può usare anche direttamente:

```powershell
python -m sld_ci_v04_beta3.alpha18_cli --pdf "C:\\percorso\\schema.pdf" --out "reports\\alpha18_esempio"
```

Per tutti i casi con etichette native il dispatch automatico precedente
(Alpha 12/15/16) rimane invariato.

## Validazione attuale

Senza consultare i TXT di riferimento, su PV3 e Settimo vengono rilevati tre
candidati graficamente simili, ciascuno con otto rami dalla sbarra e, nella
zona inferiore, tre gruppi grafici con otto compartimenti ciascuno. Il
raggruppamento spaziale **non dimostra** che quei compartimenti appartengano
all'inverter né che siano String Box. Le due tavole sono quasi duplicate:
non rappresentano validazioni indipendenti.

## Limiti da affrontare

- Interpretazione sicura dei simboli di String Box e loro conteggio.
- Ricostruzione delle connessioni verso TR/CU con tracciamento reale.
- Verifica su stili grafici differenti, non appartenenti alla stessa famiglia.
- Parametri del rilevatore da calibrare su ulteriori disegni senza overfitting.
- Output SAP completo solo dopo validazione delle cardinalità e dei parent.

Non legge Ground Truth, non usa OCR, non chiama API o servizi esterni e non
modifica lo SLD originale.
