"""Alpha13 Windows viewer: PDF evidence crop + per-inverter, scoped HITL decisions.

Provides a standalone file picker and a callable window for Alpha12 GUI. Tkinter
is imported only inside GUI functions, allowing headless unit testing.
"""
from __future__ import annotations

import base64
from pathlib import Path

from .sap.evidence_visual_alpha13 import (
    VisualReviewLedger, evidence_is_complete, markers_for_record, parse_evidence_ref,
    render_preview,
)


LEGEND = {'TR':('#1670c5','TR'), 'INV':('#d05016','INV'), 'STR_Box':('#8b3ec3','SB')}


def run_viewer(parent, report_file: Path, pdf_file: Path, output_dir: Path) -> None:
    import tkinter as tk
    from tkinter import ttk, messagebox, simpledialog
    try:
        import pymupdf as fitz
    except ImportError:
        import fitz

    ledger=VisualReviewLedger(report_file,pdf_file,output_dir)
    doc=fitz.open(pdf_file)
    top=tk.Toplevel(parent)
    top.title('Alpha 13 - Verifica visiva per singolo inverter')
    top.geometry('1300x850')
    top.minsize(1000,640)
    # The picker root is withdrawn: a transient window could stay invisible.
    top.protocol('WM_DELETE_WINDOW',lambda:(doc.close(),top.destroy()))

    main=ttk.Frame(top,padding=10); main.pack(fill='both',expand=True)
    ttk.Label(main,text=f"Impianto: {ledger.report['plant_id']}    |    PDF: {pdf_file.name}",
              font=('Segoe UI',11,'bold')).pack(anchor='w',pady=(0,5))
    ttk.Label(main,text=('CANDIDATO = ipotesi documentale. Conferma = controllo VISIVO effettuato da te, '
                         'non dimostrazione automatica della continuita elettrica.'),
              foreground='#794a0d',wraplength=1180).pack(anchor='w',pady=(0,7))

    frame=ttk.Panedwindow(main,orient='horizontal'); frame.pack(fill='both',expand=True)
    left=ttk.Frame(frame); right=ttk.Frame(frame)
    frame.add(left,weight=2);frame.add(right,weight=4)
    ttk.Label(left,text='Seleziona una riga (CU / TR / INV)').pack(anchor='w')
    fleft=ttk.Frame(left);fleft.pack(fill='both',expand=True)
    cols=('CU','TR','INV','SB','Esito')
    tree=ttk.Treeview(fleft,columns=cols,show='headings',selectmode='browse',height=27)
    for c,width in zip(cols,[44,40,44,58,145]):
        tree.heading(c,text=c);tree.column(c,width=width,anchor='center' if c!='Esito' else 'w',stretch=(c=='Esito'))
    tree.pack(side='left',fill='both',expand=True)
    bar=ttk.Scrollbar(fleft,orient='vertical',command=tree.yview);bar.pack(side='right',fill='y')
    tree.configure(yscrollcommand=bar.set)
    tree.tag_configure('confirmed',background='#d9f3de')
    tree.tag_configure('issue',background='#ffecdd')
    for i,r in enumerate(ledger.records):
        asset=r['asset_id_originale'];decision=ledger.decisions.get(asset)
        status='Confermato' if decision and decision['status']=='CONFERMATO_VISIVO' else 'Da correggere' if decision else 'Da verificare'
        tree.insert('', 'end',iid=str(i),values=(r['CU'],r['TR'] if r['TR'] is not None else '—',
            r['INV'] if r['INV'] is not None else '—',r['STR_Box'] if r['STR_Box'] is not None else '?',status),
            tags=('confirmed' if status=='Confermato' else 'issue' if status=='Da correggere' else 'normal',))

    header=ttk.Label(right,text='Apri una riga per mostrare le evidenze del PDF',font=('Segoe UI',11,'bold'))
    header.pack(anchor='w',pady=(0,6))
    image_frame=ttk.Frame(right);image_frame.pack(fill='both',expand=True)
    canvas=tk.Canvas(image_frame,width=850,height=590,background='#f4f4f4',highlightthickness=1)
    canvas.pack(fill='both',expand=True)
    details=ttk.Label(right,text='Nessun inverter selezionato',wraplength=800,justify='left')
    details.pack(anchor='w',pady=(8,5))
    ttk.Label(right,text='Blu: TR candidato   |   Arancio: inverter   |   Viola: quantità String Box',
              foreground='#555555').pack(anchor='w',pady=(0,8))
    actions=ttk.Frame(right);actions.pack(fill='x')
    btn_confirm=ttk.Button(actions,text='Conferma dati visualizzati')
    btn_confirm.pack(side='left',padx=(0,8))
    btn_flag=ttk.Button(actions,text='Da correggere')
    btn_flag.pack(side='left',padx=(0,8))
    btn_clear=ttk.Button(actions,text='Annulla verifica')
    btn_clear.pack(side='left')
    footer=ttk.Label(right,text=f'JSON HITL: {ledger.out_json.name}  (salvataggio ad ogni scelta)',
                     wraplength=800,foreground='#555555')
    footer.pack(anchor='w',pady=(8,0))
    current={'index':None,'image':None,'complete':False}

    def repaint_row(idx):
        r=ledger.records[idx]; decision=ledger.decisions.get(r['asset_id_originale'])
        status='Confermato' if decision and decision['status']=='CONFERMATO_VISIVO' else 'Da correggere' if decision else 'Da verificare'
        tree.item(str(idx),values=(r['CU'],r['TR'] if r['TR'] is not None else '—',
            r['INV'] if r['INV'] is not None else '—',r['STR_Box'] if r['STR_Box'] is not None else '?',status),
            tags=('confirmed' if status=='Confermato' else 'issue' if status=='Da correggere' else 'normal',))

    def on_selected(event=None):
        selected=tree.selection()
        if not selected:
            return
        idx=int(selected[0]); current['index']=idx
        r=ledger.records[idx]
        source_markers=markers_for_record(r,pdf_file.name)
        complete=evidence_is_complete(r,pdf_file.name)
        current['complete']=complete
        canvas.delete('all');current['image']=None
        parentrefs=parse_evidence_ref(r.get('evidenza_parent',''))
        page_number=parentrefs[0]['page'] if parentrefs else source_markers[0]['page'] if source_markers else None
        statuses=(f"CU {r['CU']}  |  TR {r.get('TR')}  |  INV {r.get('INV')} "
                  f"(etichetta originale I{r.get('slot_INV_originale')})  |  "
                  f"String Box {r.get('STR_Box')}\n"
                  f"Parent: {r.get('stato_parent')}  |  SB: {r.get('stato_string_box')} "
                  f"| Etichetta anomala: {'SI' if r.get('conflitto_etichetta') else 'NO'}")
        if not source_markers or not page_number:
            canvas.create_text(24,24,text='Evidenze grafiche mancanti; non e possibile confermare la riga.',anchor='nw')
            details.config(text=statuses+'\nMancano riferimenti grafici nel PDF.')
        else:
            try:
                png,markers,geometry=render_preview(doc[page_number-1],r,pdf_file.name)
                image=tk.PhotoImage(data=base64.b64encode(png).decode('ascii'))
                current['image']=image
                canvas.config(scrollregion=(0,0,geometry['width'],geometry['height']))
                canvas.create_image(0,0,anchor='nw',image=image)
                for m in markers:
                    color,kindlabel=LEGEND[m['kind']]
                    x,y=m['px'],m['py']
                    canvas.create_oval(x-13,y-13,x+13,y+13,outline=color,width=4)
                    rect=canvas.create_rectangle(x+16,y-26,x+64,y-3,fill=color,outline=color)
                    canvas.create_text(x+19,y-15,text=kindlabel,anchor='w',fill='white',font=('Segoe UI',10,'bold'))
                details.config(text=statuses+f'\nPDF pagina {page_number}. Cerchi sulle etichette originali; verifica i conduttori nel ritaglio.')
            except (ValueError,IndexError,RuntimeError) as ex:
                current['complete']=False
                canvas.create_text(20,20,text=f'Ritaglio non disponibile: {ex}',anchor='nw',width=700)
                details.config(text=statuses+'\nApri il PDF originale per una verifica manuale completa.')
        btn_confirm.config(state='normal' if current['complete'] else 'disabled')
        btn_flag.config(state='normal')
        btn_clear.config(state='normal' if r['asset_id_originale'] in ledger.decisions else 'disabled')

    def selected():
        idx=current['index']
        return (idx,ledger.records[idx]) if idx is not None else (None,None)

    def confirm():
        idx,r=selected()
        if r is None:return
        if not current['complete']:
            messagebox.showwarning('Evidenza incompleta','La riga non ha tutti i dati verificabili.',parent=top)
            return
        if r.get('conflitto_etichetta') and not messagebox.askyesno('Etichetta anomala',
            'L etichetta dell inverter presenta un conflitto nel PDF. Hai verificato manualmente l identita corretta?',
            default='no',parent=top):return
        if not messagebox.askyesno('Conferma individuale',
            f"Hai verificato nello SLD CU {r['CU']} / TR {r['TR']} / INV {r['INV']} "
            f"e {r['STR_Box']} String Box?\n\n"
            'Registrare soltanto questa riga come confermata VISIVAMENTE?\n'
            'Non equivale a una prova di continuita elettrica automatica.',
            default='no',parent=top):return
        try:ledger.set_decision(r['asset_id_originale'],'CONFERMATO_VISIVO')
        except (ValueError,OSError) as ex:
            messagebox.showerror('Verifica non salvata',str(ex),parent=top);return
        repaint_row(idx);on_selected()

    def flag():
        idx,r=selected()
        if r is None:return
        note=simpledialog.askstring('Da correggere',
              'Descrivi la differenza osservata nel PDF (es. parent corretto, String Box, etichetta).\n'
              'Non verra applicata alcuna correzione automatica.',parent=top)
        if note is None:return
        try:ledger.set_decision(r['asset_id_originale'],'DA_CORREGGERE',note)
        except (ValueError,OSError) as ex:
            messagebox.showerror('Segnalazione non salvata',str(ex),parent=top);return
        repaint_row(idx);on_selected()

    def clear():
        idx,r=selected()
        if r is None:return
        if messagebox.askyesno('Annulla verifica','Rimuovere la decisione salvata su questa sola riga?',default='no',parent=top):
            ledger.clear_decision(r['asset_id_originale']);repaint_row(idx);on_selected()

    tree.bind('<<TreeviewSelect>>',on_selected)
    btn_confirm.configure(command=confirm)
    btn_flag.configure(command=flag)
    btn_clear.configure(command=clear)
    if ledger.records:
        tree.selection_set('0');tree.see('0');on_selected()
    top.grab_set()
    parent.wait_window(top)


def main():
    import tkinter as tk
    from tkinter import filedialog,messagebox
    root=tk.Tk();root.withdraw()
    root.attributes('-topmost',True)
    project_root=Path(__file__).resolve().parent.parent
    try:
        folder=filedialog.askdirectory(parent=root,title='Scegli la cartella dei risultati Alpha12',
              initialdir=str(project_root/'reports'/'sap_alpha12') if (project_root/'reports'/'sap_alpha12').exists() else str(project_root))
        if not folder:return 0
        report=Path(folder)/'alpha12_riepilogo.json'
        if not report.is_file():
            messagebox.showerror('Report mancante','Non trovo alpha12_riepilogo.json nella cartella scelta.',parent=root)
            return 2
        pdf=filedialog.askopenfilename(parent=root,title='Seleziona il PDF originale dello SLD',
              filetypes=[('Documenti PDF','*.pdf')],initialdir=str(project_root))
        if not pdf:return 0
        try:run_viewer(root,report,Path(pdf),Path(folder))
        except (ValueError,OSError,RuntimeError,KeyError) as ex:
            messagebox.showerror('Verifica non avviata',str(ex),parent=root)
            return 2
        return 0
    finally:
        root.destroy()


if __name__ == '__main__':
    raise SystemExit(main())
