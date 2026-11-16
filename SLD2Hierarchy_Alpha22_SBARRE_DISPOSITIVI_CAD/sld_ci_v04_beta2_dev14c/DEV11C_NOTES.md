# dev11c — GUI startup fix

Bugfix puro rispetto a dev11b.

- Corretto l'ordine di inizializzazione Tkinter in `operator_feeder.py`.
- La finestra `tk.Tk()` viene ora creata prima di `tk.StringVar`.
- `self.mode` usa esplicitamente `master=self.root`.
- Nessuna modifica alla logica di analisi, ai resolver, alla calibrazione feeder o ai formati JSON.
- Compatibilità invariata con gli output dev10 usati come `--analysis`.
