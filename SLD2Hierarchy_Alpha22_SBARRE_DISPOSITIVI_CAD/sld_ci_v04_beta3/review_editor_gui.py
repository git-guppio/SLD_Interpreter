"""Finestra di review operatore per i CAD vettoriali (sostituisce il JSON scritto a mano).

Uso dal workbench (dopo un'analisi CAD) oppure da riga di comando::

    python -m sld_ci_v04_beta3.review_editor_gui --run <cartella_esecuzione> --pdf <PDF>

La finestra mostra la bozza precompilata dai percorsi disegnati, lascia
modificare CU/TR di ogni inverter e richiede le conferme esplicite
dell'operatore. Salva solo una review che supera lo stesso validatore della CLI.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .sap.cad_review_draft import (DRAFT_NAME, draft_for_run, finalize_review,
                                   validate_against_run)

REVIEW_NAME = 'review_operatore_confermata.json'


def save_review(review, run_dir) -> Path:
    path = Path(run_dir) / REVIEW_NAME
    path.write_text(json.dumps(review, ensure_ascii=False, indent=2), encoding='utf-8')
    return path


def open_review_editor(parent, run_dir, pdf_path, plant_id=None, on_saved=None):
    """Apre la finestra (Toplevel se ``parent`` e dato). Ritorna la finestra."""
    import tkinter as tk
    from tkinter import messagebox, ttk

    run_dir, pdf_path = Path(run_dir), Path(pdf_path)
    draft = draft_for_run(run_dir, pdf_path, plant_id)
    (run_dir / DRAFT_NAME).write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding='utf-8')

    win = tk.Toplevel(parent) if parent is not None else tk.Tk()
    win.title('Review operatore CAD - conferma CU / TR / String Box')
    win.minsize(640, 420)
    frame = ttk.Frame(win, padding=14)
    frame.pack(fill='both', expand=True)
    ttk.Label(frame, text=f'Impianto {draft["plant_id"]}   |   PDF {pdf_path.name}',
              font=('Segoe UI', 11, 'bold')).pack(anchor='w')
    ttk.Label(frame, text=('TR proposto dai percorsi disegnati (sbarra e interruttori in serie). '
                           'La CU NON e dedotta dal disegno: controllala.'),
              wraplength=600).pack(anchor='w', pady=(2, 10))

    rows = draft['parent_confirmations']
    if not rows:
        ttk.Label(frame, foreground='#b91c1c', wraplength=600,
                  text=('Nessun gruppo QPS completo in questa esecuzione: impossibile preparare la '
                        'review. Verifica che Tesseract OCR sia installato e rilancia l\'analisi.')).pack(anchor='w')
        ttk.Button(frame, text='Chiudi', command=win.destroy).pack(anchor='e', pady=10)
        return win

    table = ttk.Frame(frame)
    table.pack(fill='x')
    for col, title in enumerate(('Gruppo QPS', 'Inverter grafico', 'CU', 'TR', 'INV', 'Origine TR')):
        ttk.Label(table, text=title, font=('Segoe UI', 9, 'bold')).grid(row=0, column=col, padx=6, sticky='w')
    variables = []
    for i, r in enumerate(rows, start=1):
        cu, tr = tk.StringVar(value=str(r['CU'])), tk.StringVar(value='' if r['TR'] is None else str(r['TR']))
        variables.append((cu, tr))
        ttk.Label(table, text=str(r['qps_group'])).grid(row=i, column=0, padx=6, sticky='w')
        ttk.Label(table, text=r['_inverter_grafico'] or '').grid(row=i, column=1, padx=6, sticky='w')
        ttk.Spinbox(table, from_=1, to=999, width=5, textvariable=cu).grid(row=i, column=2, padx=6)
        ttk.Spinbox(table, from_=1, to=999, width=5, textvariable=tr).grid(row=i, column=3, padx=6)
        ttk.Label(table, text=str(r['INV'])).grid(row=i, column=4, padx=6)
        ttk.Label(table, text=r['_fonte_TR'],
                  foreground='#15803d' if r['_fonte_TR'] == 'PERCORSO_DISEGNATO' else '#b45309'
                  ).grid(row=i, column=5, padx=6, sticky='w')

    sb_var, num_var = tk.BooleanVar(value=False), tk.BooleanVar(value=False)
    ttk.Separator(frame).pack(fill='x', pady=10)
    ttk.Checkbutton(frame, variable=sb_var,
                    text='Confermo: i QPS sono Quadri Parallelo Stringhe = String Box SAP').pack(anchor='w')
    ttk.Checkbutton(frame, variable=num_var,
                    text='Confermo: in QPS-n-k/N il numero n identifica l\'inverter n').pack(anchor='w')
    ttk.Label(frame, text='Riferimento della verifica (chi, quando, su quale documento/pagina):').pack(anchor='w', pady=(10, 2))
    evidence = ttk.Entry(frame, width=90)
    evidence.pack(fill='x')

    def on_save():
        try:
            edited = []
            for r, (cu, tr) in zip(rows, variables):
                if not cu.get().strip().isdigit() or not tr.get().strip().isdigit():
                    raise ValueError(f'CU e TR del gruppo QPS {r["qps_group"]} devono essere numeri interi.')
                edited.append({**r, 'CU': int(cu.get()), 'TR': int(tr.get())})
            review = finalize_review(draft, operator_evidence=evidence.get(),
                                     confirm_qps_is_string_box=sb_var.get(),
                                     confirm_numbering=num_var.get(), rows=edited)
            validate_against_run(review, pdf_path, run_dir)
        except ValueError as exc:
            messagebox.showerror('Review non valida', str(exc), parent=win)
            return
        path = save_review(review, run_dir)
        messagebox.showinfo('Review salvata', f'Review valida salvata in:\n{path}', parent=win)
        win.destroy()
        if on_saved:
            on_saved(path)

    buttons = ttk.Frame(frame)
    buttons.pack(fill='x', pady=(12, 0))
    ttk.Button(buttons, text='Annulla', command=win.destroy).pack(side='right')
    ttk.Button(buttons, text='Valida e salva', command=on_save).pack(side='right', padx=8)
    return win


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='Review operatore CAD da bozza precompilata')
    p.add_argument('--run', required=True, type=Path, help='Cartella di un\'esecuzione Alpha22')
    p.add_argument('--pdf', required=True, type=Path)
    p.add_argument('--plant-id')
    p.add_argument('--solo-bozza', action='store_true', help='Scrive solo la bozza JSON, senza finestra')
    a = p.parse_args(argv)
    try:
        if a.solo_bozza:
            draft = draft_for_run(a.run, a.pdf, a.plant_id)
            out = a.run / DRAFT_NAME
            out.write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding='utf-8')
            print('Bozza (NON valida finche non confermata):', out)
            return 0
        win = open_review_editor(None, a.run, a.pdf, a.plant_id)
        win.mainloop()
    except (OSError, ValueError, KeyError) as exc:
        p.exit(2, f'[ERRORE review] {exc}\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
