# Alpha 12 — selezione file tramite finestre Windows

Questa e una **aggiunta facoltativa** alla precedente Alpha 12. Il motore di riconoscimento e l'esportatore Excel/CSV non sono stati modificati.

## Come usarla

1. Apri `AVVIA_ALPHA12_CON_FINESTRA.bat` con un doppio clic, oppure esegui `\.\AVVIA_ALPHA12_CON_FINESTRA.bat` in PowerShell.
2. Nella finestra Windows scegli il **PDF** dello schema unifilare, senza copiarne il percorso.
3. Conferma l'**identificativo impianto** proposto dal nome del PDF (ad esempio `PV11_Pampa_Norte`) o modificalo.
4. Quando viene chiesto il **JSON HITL**, per la prima prova premi **No**. Se vuoi usare una review effettivamente approvata e circoscritta, scegli **Si** e seleziona il file tramite finestra.
5. Al termine scegli se aprire la cartella dei risultati.

I risultati restano nella cartella `reports/sap_alpha12/<identificativo impianto>/` e comprendono `alpha12_CU_TR_INV_STR_Box.csv` e `alpha12_gerarchie_stereotipi.xlsx`.

Se esistono gia report per lo stesso impianto, una conferma esplicita e richiesta prima di sovrascriverli. **PDF e JSON di input non vengono modificati.** Chiudere la finestra di selezione senza scegliere nulla annulla la procedura.

Il vecchio file `esporta_gerarchia_stereotipi_PDF.bat` resta disponibile e funzionante per chi preferisce immettere i percorsi manualmente.

### Requisito

Python con `tkinter` (normalmente incluso nella distribuzione Python per Windows). Se `tkinter` non e installato, il programma lo segnala senza alterare il progetto; usa allora il vecchio `.bat` manuale.

### Limite tecnico

Le finestre Windows selezionano **file e percorsi**, non verificano la correttezza delle associazioni elettriche. Le relazioni TR–INV candidate e le evidenze HITL conservano il medesimo significato di Alpha 12.
