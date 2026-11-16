"""Workbench Windows unificato (GUI principale) del prototipo SAP-first PV.

Il nome del modulo (``alpha16``) e storico e resta per compatibilita con i
test e con AVVIA_SLD2HIERARCHY.bat; la versione mostrata in GUI viene da
``sld_ci_v04_beta3.__version__``.

UI orchestration only. The Alpha10-12 recognition/export engine and the
Alpha13 per-inverter viewer are imported unchanged. No network requests.
Each execution writes to a new run folder; the source PDF is read-only.
"""
from __future__ import annotations

import csv
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading

from . import __version__
from .sap_picker_gui import default_plant_id, valid_plant_id
from .sap.evidence_visual_alpha13 import LEDGER_FILENAME, load_evidence
from .engines import engine_by_mode, select_engine

REPORT_NAME = 'alpha12_riepilogo.json'
XLSX_NAME = 'alpha12_gerarchie_stereotipi.xlsx'
CSV_NAME = 'alpha12_CU_TR_INV_STR_Box.csv'
ROOT_SUBPATH = Path('reports') / 'sap_alpha16'


def next_run_directory(project_root: Path, plant_id: str, *, now: str | None = None) -> Path:
    """Never overwrite previous analyses, even two runs within the same second."""
    if not valid_plant_id(plant_id):
        raise ValueError('Identificativo impianto non valido.')
    ts = now or datetime.now().strftime('%Y%m%d_%H%M%S')
    base = project_root / ROOT_SUBPATH / plant_id
    candidate = base / ts
    number = 2
    while candidate.exists():
        candidate = base / f'{ts}_{number:02d}'
        number += 1
    return candidate


def load_report_folder(folder: Path) -> dict:
    """Load an actual Alpha12-compatible report, never a TXT ground truth."""
    report_path = Path(folder) / REPORT_NAME
    if not report_path.is_file():
        raise ValueError('La cartella non contiene alpha12_riepilogo.json.')
    try:
        data = json.loads(report_path.read_text(encoding='utf-8-sig'))
    except (OSError, ValueError) as exc:
        raise ValueError('Report JSON non leggibile.') from exc
    if data.get('schema') != 'sld-sap-stereotypes-alpha12/v1':
        raise ValueError('Il report selezionato non e un output Alpha12 valido.')
    if not isinstance(data.get('plant_id'), str) or not data['plant_id'].startswith('CI::'):
        raise ValueError('Identificativo impianto mancante nel report.')
    if not isinstance(data.get('summary'), dict) or not isinstance(data.get('evidence'), list):
        raise ValueError('Il report e incompleto.')
    return data


def find_source_pdf(report: dict) -> Path | None:
    raw = report.get('source_pdf')
    if not isinstance(raw, str) or not raw:
        return None
    p = Path(raw)
    return p if p.is_file() and p.suffix.lower() == '.pdf' else None


def validate_alpha13_review(report_folder: Path, pdf_file: Path) -> tuple[Path, int]:
    """Source-bound, explicitly approved per-inverter reviews only.

    Reject historical broad confirmations and outdated PDF/report revisions.
    Does not alter records or promote parentage by itself.
    """
    report_folder = Path(report_folder)
    pdf_file = Path(pdf_file)
    report = load_report_folder(report_folder)
    ledger_file = report_folder / LEDGER_FILENAME
    if not ledger_file.is_file():
        raise ValueError('Non esiste un registro HITL Alpha13: verifica prima almeno un inverter.')
    if not pdf_file.is_file() or pdf_file.suffix.lower() != '.pdf':
        raise ValueError('PDF originale non trovato.')
    load_evidence(report_folder / REPORT_NAME, pdf_file)  # checks PDF filename + report shape
    data = json.loads(ledger_file.read_text(encoding='utf-8-sig'))
    source = data.get('alpha13_source', {})
    if (data.get('schema') != 'sld-sap-alpha10-reviewed-parentage/v1' or
            data.get('plant_id') != report['plant_id'] or
            source.get('report_sha256') != hashlib.sha256((report_folder / REPORT_NAME).read_bytes()).hexdigest() or
            source.get('pdf_sha256') != hashlib.sha256(pdf_file.read_bytes()).hexdigest()):
        raise ValueError('Il registro HITL non corrisponde esattamente al PDF e al report selezionati.')
    entries = data.get('confirmed_tr_inverter_groups')
    if not isinstance(entries, list) or not entries:
        raise ValueError('Nessuna associazione confermata. Le sole segnalazioni non modificano l Excel.')
    checks = data.get('alpha13_visual_checks', [])
    if not isinstance(checks, list):
        raise ValueError('Verifiche visive non valide nel JSON HITL.')
    confirmed = [c for c in checks if isinstance(c, dict) and c.get('status') == 'CONFERMATO_VISIVO']
    if len(entries) != len(confirmed):
        raise ValueError('Numero conferme nel JSON non coerente: non applicare il registro.')
    return ledger_file, len(entries)


def portfolio_rows(project_root: Path) -> list[dict]:
    """Summarize only real output runs. No accuracy estimates from counts."""
    base = Path(project_root) / ROOT_SUBPATH
    rows = []
    if not base.exists():
        return rows
    for report_path in sorted(base.glob('*/*/' + REPORT_NAME)):
        try:
            report = load_report_folder(report_path.parent)
            s = report['summary']
            rows.append({
                'impianto': report['plant_id'], 'esecuzione': report_path.parent.name,
                'pdf': Path(str(report.get('source_pdf', ''))).name,
                'CU_rilevate': s.get('cu', 0), 'TR_candidati': s.get('tr', 0),
                'INV_candidati': s.get('inverters', 0),
                'SB_quantita_documentate': s.get('string_box_quantity_total_resolved', 0),
                'INV_SB_non_risolte': s.get('string_box_quantities_unresolved', 0),
                'parent_TR_INV_candidati_o_HITL': s.get('tr_inverter_parent_candidates_or_confirmed', 0),
                'parent_HITL_confermati': s.get('tr_inverter_parent_hitl_confirmed', 0),
                'TR_per_CU_uniformi': 'SI' if s.get('stereotype_tr_uniform_all_cus') else 'NO',
                'INV_per_TR_uniformi': 'SI' if s.get('stereotype_inv_uniform_all_trs') else 'NO',
                'import_Matrix_FLOW_certificato': 'NO',
                'report_json': str(report_path),
            })
        except (OSError, ValueError, TypeError, KeyError):
            # Skip incomplete reports, do not present as successful runs.
            continue
    # Add Alpha15 indexed-tag runs. A blank SB quantity is not zero equipment;
    # the resolved total may be partial. Keep that distinction in the note.
    for report_path in sorted(base.glob('*/*/alpha15_diagnostica.json')):
        try:
            data=json.loads(report_path.read_text(encoding='utf8'))
            if data.get('schema')!='sld-sap-multistyle-alpha15/v1':continue
            s=data['summary']
            rows.append({
              'impianto':data['plant_id'],'esecuzione':report_path.parent.name,
              'pdf':Path(str(data['source_pdf'])).name,
              'CU_rilevate':s['cu'],'TR_candidati':s['tr_candidate'],
              'INV_candidati':s['inverters'],
              'SB_quantita_documentate':s['box_quantity_total_complete_only'],
              'INV_SB_non_risolte':s['box_quantities_unresolved'],
              'parent_TR_INV_candidati_o_HITL':s['parent_candidates'],
              'parent_HITL_confermati':0,
              'TR_per_CU_uniformi':'NON CERTIFICATO',
              'INV_per_TR_uniformi':'NON CERTIFICATO',
              'import_Matrix_FLOW_certificato':'NO','report_json':str(report_path),
              'metodo':'Alpha15 - codifiche indicizzate',
              'nota':'Somma SB PARZIALE, con lacune' if s['box_quantities_unresolved'] else 'Sequenze ID SB complete; verifica indipendente ancora necessaria',
            })
        except (OSError,ValueError,KeyError,TypeError):continue
    # Alpha16 LVL-SB indexed runs are source-derived counts, never accuracy metrics.
    for report_path in sorted(base.glob('*/*/alpha16_diagnostica.json')):
        try:
            data=json.loads(report_path.read_text(encoding='utf8'))
            if data.get('schema')!='sld-sap-lvl-indexed-alpha16/v1':continue
            s=data['summary']
            rows.append({
                'impianto':data['plant_id'],'esecuzione':report_path.parent.name,
                'pdf':Path(str(data['source_pdf'])).name,
                'CU_rilevate':s['cu'],'TR_candidati':s['tr_candidate'],
                'INV_candidati':s['inverters'],
                'SB_quantita_documentate':s['box_quantity_total_complete_only'],
                'INV_SB_non_risolte':s['box_quantities_unresolved'],
                'parent_TR_INV_candidati_o_HITL':s['parent_candidates'],
                'parent_HITL_confermati':0,
                'TR_per_CU_uniformi':'NON CERTIFICATO',
                'INV_per_TR_uniformi':'NON CERTIFICATO',
                'import_Matrix_FLOW_certificato':'NO',
                'report_json':str(report_path),'metodo':'Alpha16 - etichette LVL-SB',
                'nota':'Parent TR proposti da geometria, nessuna continuita verificata',
            })
        except (OSError,ValueError,KeyError,TypeError):continue
    # Alpha18: structural candidates from vector-only CAD. These are NOT
    # verified assets; never import them into Matrix FLOW or report as recall.
    for report_path in sorted(base.glob('*/*/alpha18_candidati_vettoriali.json')):
        try:
            data=json.loads(report_path.read_text(encoding='utf8'))
            if data.get('schema')!='sld-alpha18-cad-candidates/v1':continue
            n=len(data.get('converter_candidates',[]))
            hypothesis_path=report_path.parent/'alpha19_ipotesi_grafiche.json'
            n_spatial=0
            if hypothesis_path.is_file():
                alpha19=json.loads(hypothesis_path.read_text(encoding='utf8'))
                if alpha19.get('schema')=='sld-alpha19-vector-hypotheses/v1':
                    n_spatial=alpha19['summary']['non_electrical_spatial_proposals']
            # Alpha21 CAD: documentary QPS counts and operator-confirmed SAP
            # structure must be reported distinctly from unreviewed candidates.
            alpha21_path=report_path.parent/'alpha21_diagnostica_qps.json'
            sap21_path=report_path.parent/'alpha21_riepilogo.json'
            qps_count=None;reviewed_summary=None
            if alpha21_path.is_file():
                a21=json.loads(alpha21_path.read_text(encoding='utf8'))
                if a21.get('schema')=='sld-alpha21-qps-source-evidence/v1':
                    qps_count=a21['summary']['qps_documented_total']
            if sap21_path.is_file():
                sap21=json.loads(sap21_path.read_text(encoding='utf8'))
                if sap21.get('schema')=='sld-sap-stereotypes-alpha12/v1':
                    reviewed_summary=sap21['summary']
            rows.append({
                'impianto':report_path.parent.parent.name,
                'esecuzione':report_path.parent.name,
                'pdf':Path(str(data['source_pdf'])).name,
                'CU_rilevate':reviewed_summary['cu'] if reviewed_summary else 'NON RISOLTO',
                'TR_candidati':reviewed_summary['tr'] if reviewed_summary else 'NON RISOLTO',
                'INV_candidati':reviewed_summary['inverters'] if reviewed_summary else f'{n} GRAFICI NON CONFERMATI',
                'SB_quantita_documentate':reviewed_summary['string_box_quantity_total_resolved'] if reviewed_summary else 'NON RISOLTO',
                'INV_SB_non_risolte':reviewed_summary['string_box_quantities_unresolved'] if reviewed_summary else 'NON QUANTIFICABILI',
                'parent_TR_INV_candidati_o_HITL':reviewed_summary['tr_inverter_parent_candidates_or_confirmed'] if reviewed_summary else 'NESSUNO',
                'parent_HITL_confermati':reviewed_summary['tr_inverter_parent_hitl_confirmed'] if reviewed_summary else 0,
                'TR_per_CU_uniformi':'NON VALUTABILE',
                'INV_per_TR_uniformi':'NON VALUTABILE',
                'import_Matrix_FLOW_certificato':'NO',
                'report_json':str(report_path),
                'metodo':('Alpha21 - QPS e gerarchia verificata operatore' if (report_path.parent/'alpha21_riepilogo.json').is_file() else 'Alpha21 - QPS fonte PDF' if (report_path.parent/'alpha21_diagnostica_qps.json').is_file() else 'Alpha20 - tratti CAD fino ai morsetti' if (report_path.parent/'alpha20_conduttori_ingresso.json').is_file() else 'Alpha19 - ipotesi CAD ordinali') if hypothesis_path.is_file() else 'Alpha18 - topologia vettoriale',
                'nota':f"{n} candidati e {n_spatial} ipotesi di campo; morsetti opzionali, NESSUNA connessione SAP confermata",
            })
        except (OSError,ValueError,KeyError,TypeError):continue
    # Alpha17 vector-only diagnostics: UNKNOWN counts are not zero devices.
    for report_path in sorted(base.glob('*/*/alpha17_diagnostica_geometrica.json')):
        try:
            if (report_path.parent/'alpha18_candidati_vettoriali.json').is_file():continue
            data=json.loads(report_path.read_text(encoding='utf8'))
            if data.get('schema')!='sld-alpha17-vector-triage/v1':continue
            # Alpha21 CAD: documentary QPS counts and operator-confirmed SAP
            # structure must be reported distinctly from unreviewed candidates.
            alpha21_path=report_path.parent/'alpha21_diagnostica_qps.json'
            sap21_path=report_path.parent/'alpha21_riepilogo.json'
            qps_count=None;reviewed_summary=None
            if alpha21_path.is_file():
                a21=json.loads(alpha21_path.read_text(encoding='utf8'))
                if a21.get('schema')=='sld-alpha21-qps-source-evidence/v1':
                    qps_count=a21['summary']['qps_documented_total']
            if sap21_path.is_file():
                sap21=json.loads(sap21_path.read_text(encoding='utf8'))
                if sap21.get('schema')=='sld-sap-stereotypes-alpha12/v1':
                    reviewed_summary=sap21['summary']
            rows.append({
                'impianto':report_path.parent.parent.name,
                'esecuzione':report_path.parent.name,
                'pdf':Path(str(data['source_pdf'])).name,
                'CU_rilevate':reviewed_summary['cu'] if reviewed_summary else 'NON RISOLTO',
                'TR_candidati':reviewed_summary['tr'] if reviewed_summary else 'NON RISOLTO',
                'INV_candidati':'NON RISOLTO','SB_quantita_documentate':'NON RISOLTO',
                'INV_SB_non_risolte':'NON QUANTIFICABILI',
                'parent_TR_INV_candidati_o_HITL':'NESSUNO',
                'parent_HITL_confermati':0,
                'TR_per_CU_uniformi':'NON VALUTABILE',
                'INV_per_TR_uniformi':'NON VALUTABILE',
                'import_Matrix_FLOW_certificato':'NO',
                'report_json':str(report_path),
                'metodo':'Alpha17 - diagnostica vettoriale',
                'nota':f"{len(data.get('geometric_repeat_groups',[]))} classi di ripetizioni grafiche NON identificate come asset SAP"
            })
        except (OSError,ValueError,KeyError,TypeError):continue
    return rows


def write_portfolio_csv(project_root: Path) -> tuple[Path, int]:
    rows = portfolio_rows(project_root)
    for row in rows:
        row.setdefault('metodo','Alpha12 - etichette geometriche')
        row.setdefault('nota','Stereotipi documentali, parent non verificati elettricamente')
    out = Path(project_root) / ROOT_SUBPATH / 'RIEPILOGO_PROVE_SLD.csv'
    out.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        'impianto', 'esecuzione', 'pdf', 'CU_rilevate', 'TR_candidati', 'INV_candidati',
        'SB_quantita_documentate', 'INV_SB_non_risolte', 'parent_TR_INV_candidati_o_HITL',
        'parent_HITL_confermati', 'TR_per_CU_uniformi', 'INV_per_TR_uniformi',
        'import_Matrix_FLOW_certificato', 'report_json', 'metodo', 'nota',
    ]
    with out.open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, delimiter=';')
        writer.writeheader()
        writer.writerows(rows)
    return out, len(rows)


def choose_recognition_mode(pdf_path: Path, review=None) -> str:
    """Identificativo del motore scelto per il PDF (vedi ``engines.registry``).

    Mantenuta per compatibilita: la logica di scelta vive nel registro.
    """
    return select_engine(pdf_path, review).mode


def write_normalized_hierarchy(mode: str, destination: Path) -> str:
    """Scrive gerarchia_normalizzata.csv/.json e restituisce una riga di log."""
    hierarchy = engine_by_mode(mode).load_hierarchy(destination)
    if not hierarchy.rows:
        return '[GERARCHIA NORMALIZZATA] nessuna riga CU/TR/INV prodotta dal motore.'
    paths = hierarchy.write(destination)
    s = hierarchy.summary()
    return ('[GERARCHIA NORMALIZZATA] '
            f'inverter={s["righe_inverter"]}, parent confermati={s["parent_confermati_operatore"]}, '
            f'proposti={s["parent_proposti"]}, non risolti={s["parent_non_risolti"]}, '
            f'SB risolte={s["string_box_totale_risolto"]} -> {paths["csv"].name}')


def main() -> int:
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk
    except ImportError:
        print('Tkinter non disponibile: usa strumenti\\esporta_gerarchia_stereotipi_PDF.bat (modalita manuale).')
        return 3

    project_root = Path(__file__).resolve().parent.parent
    root = tk.Tk()
    root.title(f'SLD2Hierarchy  |  Workbench SAP PV - v{__version__} (Alpha 22)')
    root.geometry('940x715')
    root.minsize(770, 600)
    style = ttk.Style(root)
    if 'clam' in style.theme_names():
        style.theme_use('clam')
    style.configure('Headline.TLabel', font=('Segoe UI', 17, 'bold'))
    style.configure('Sub.TLabel', font=('Segoe UI', 10), foreground='#4a5664')
    style.configure('Action.TButton', font=('Segoe UI', 10, 'bold'), padding=(13, 12))

    main_frame = ttk.Frame(root, padding=19)
    main_frame.pack(fill='both', expand=True)
    ttk.Label(main_frame, text='SLD2Hierarchy — riconoscimento multistile da SLD', style='Headline.TLabel').pack(anchor='w')
    ttk.Label(main_frame, text='Fotovoltaico con inverter centralizzati  |  Staging, non import Matrix FLOW certificato',
              style='Sub.TLabel').pack(anchor='w', pady=(3, 15))

    paths = ttk.LabelFrame(main_frame, text='Documento e risultati selezionati', padding=12)
    paths.pack(fill='x', pady=(0, 12))
    pdf_var = tk.StringVar(value='Nessun PDF selezionato')
    report_var = tk.StringVar(value='Nessun report selezionato')
    plant_var = tk.StringVar()
    status_var = tk.StringVar(value='Pronto. Le analisi precedenti non vengono sovrascritte.')
    buttons: list = []
    busy = {'running': False}
    active = {'pdf': None, 'report': None}
    events: queue.Queue = queue.Queue()

    def show_error(title, err):
        messagebox.showerror(title, str(err), parent=root)

    def select_pdf(initial=None):
        initialdir = str(initial) if initial and Path(initial).is_dir() else str(project_root)
        chosen = filedialog.askopenfilename(parent=root, title='Seleziona lo SLD originale in PDF',
                                            initialdir=initialdir,
                                            filetypes=[('PDF', '*.pdf')])
        if not chosen:
            return None
        pdf = Path(chosen)
        if not pdf.is_file():
            show_error('PDF', 'File non trovato.')
            return None
        active['pdf'] = pdf
        pdf_var.set(str(pdf))
        plant_var.set(default_plant_id(pdf))
        return pdf

    def select_report():
        folder = filedialog.askdirectory(parent=root, title='Seleziona la cartella contenente alpha12_riepilogo.json',
                                         initialdir=str(project_root / 'reports') if (project_root/'reports').is_dir() else str(project_root))
        if not folder:
            return False
        try:
            data = load_report_folder(Path(folder))
        except ValueError as ex:
            show_error('Report non valido', ex)
            return False
        active['report'] = Path(folder)
        report_var.set(str(folder))
        plant_var.set(data['plant_id'].removeprefix('CI::'))
        existing = find_source_pdf(data)
        if existing:
            active['pdf'] = existing
            pdf_var.set(str(existing))
        else:
            active['pdf'] = None
            pdf_var.set('PDF originale da selezionare per questa verifica')
        return True

    def ensure_report():
        if active['report'] is None and not select_report():
            return None
        return active['report']

    def ensure_report_pdf(folder):
        data = load_report_folder(folder)
        pdf = active['pdf']
        if pdf is not None and pdf.is_file() and pdf.name.lower() == Path(str(data.get('source_pdf', ''))).name.lower():
            return pdf
        old = find_source_pdf(data)
        if old:
            active['pdf'] = old
            pdf_var.set(str(old))
            return old
        return select_pdf()

    row1 = ttk.Frame(paths); row1.pack(fill='x', pady=3)
    ttk.Label(row1, text='PDF:', width=9).pack(side='left')
    ttk.Label(row1, textvariable=pdf_var, foreground='#183a54').pack(side='left', fill='x', expand=True)
    b_pdf=ttk.Button(row1, text='Scegli PDF', command=select_pdf); b_pdf.pack(side='right')
    row2=ttk.Frame(paths);row2.pack(fill='x', pady=3)
    ttk.Label(row2,text='Impianto:',width=9).pack(side='left')
    ttk.Entry(row2,textvariable=plant_var,width=34).pack(side='left')
    ttk.Label(row2,text='Identificativo modificabile', style='Sub.TLabel').pack(side='left',padx=10)
    row3=ttk.Frame(paths);row3.pack(fill='x', pady=3)
    ttk.Label(row3,text='Report:',width=9).pack(side='left')
    ttk.Label(row3,textvariable=report_var,foreground='#183a54').pack(side='left',fill='x',expand=True)
    b_report=ttk.Button(row3,text='Scegli report',command=select_report);b_report.pack(side='right')

    actions=ttk.LabelFrame(main_frame,text='Operazioni',padding=12)
    actions.pack(fill='x',pady=(0,12))
    for i in range(2):
        actions.columnconfigure(i,weight=1,uniform='buttons')

    def log(message):
        console.configure(state='normal')
        console.insert('end',message+'\n')
        console.see('end')
        console.configure(state='disabled')

    def set_busy(value):
        busy['running']=value
        for b in buttons:
            b.configure(state='disabled' if value else 'normal')
        status_var.set('Elaborazione in corso: attendi il risultato in questa finestra.' if value else
                       'Pronto. Puoi continuare con la verifica o con un altro SLD.')

    def start_engine(pdf, plant_id, review=None, cad_review=None):
        try:
            destination = next_run_directory(project_root, plant_id)
            engine=select_engine(pdf,review)
            mode=engine.mode
            # Review Alpha13 -> motore a etichette; review CAD -> motore vettoriale.
            engine_review=review if review is not None else (cad_review if mode=='alpha21-cad' else None)
            cmd=engine.build_command(pdf,plant_id,destination,engine_review)
        except (ValueError, OSError) as ex:
            show_error('Impossibile avviare', ex);return
        log('--- Analisi SLD ---')
        log(f'Metodo: {engine.label} [{mode}]')
        log('Sorgente: '+str(pdf))
        log('Impianto: '+plant_id)
        log('HITL: '+ (str(review) if review else 'nessuno'))
        log('Output: '+str(destination))
        set_busy(True)

        def worker():
            try:
                process=subprocess.Popen(cmd,cwd=project_root,stdout=subprocess.PIPE,
                                         stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace')
                assert process.stdout is not None
                for line in process.stdout:
                    events.put(('line',line.rstrip()))
                code=process.wait()
                if code==0:
                    try:
                        events.put(('line',write_normalized_hierarchy(mode,destination)))
                    except (OSError,ValueError,KeyError) as ex:
                        events.put(('line',f'[GERARCHIA NORMALIZZATA] non scritta: {ex}'))
                events.put(('finished',code,destination,pdf,mode))
            except OSError as ex:
                events.put(('error',str(ex)))
        threading.Thread(target=worker,daemon=True).start()

    def analyze():
        pdf=active['pdf'] if active['pdf'] is not None and active['pdf'].is_file() else select_pdf()
        if not pdf:return
        plant_id=plant_var.get().strip()
        if not valid_plant_id(plant_id):
            show_error('Identificativo non valido','Usa lettere, numeri, trattino e underscore, senza spazi.');return
        # On CAD without native text, a PDF-hash-scoped operator review is
        # entirely optional. Never load one by guessing the site filename.
        cad_review=None
        if choose_recognition_mode(pdf)=='alpha21-cad':
            if messagebox.askyesno('Gerarchia CAD: conferma operatore',
                'Hai gia un file JSON Alpha21 di conferma tecnica CU/TR/QPS per QUESTO PDF?\n\n'
                'SI: scegli il file (viene validato con hash PDF e plant ID).\n'
                'NO: analizza solo etichette e simboli, senza inventare gerarchie SAP.',
                default=messagebox.NO,parent=root):
                chosen=filedialog.askopenfilename(parent=root,title='Seleziona review tecnica Alpha21',
                                                  filetypes=[('JSON','*.json')])
                if not chosen:return
                cad_review=Path(chosen)
        start_engine(pdf,plant_id,cad_review=cad_review)

    def visual_review():
        folder=ensure_report()
        if folder is None:return
        try:
            pdf=ensure_report_pdf(folder)
            if pdf is None:return
            from .sap_visual_review_gui import run_viewer
            log('Apertura verifica visiva: '+str(folder))
            run_viewer(root, folder/REPORT_NAME, pdf, folder)
            status_var.set('Verifica visiva chiusa. Le decisioni sono salvate nei report selezionati.')
        except (ValueError,OSError,RuntimeError,KeyError) as ex:
            show_error('Verifica non avviata',ex)

    def regenerate():
        folder=ensure_report()
        if folder is None:return
        try:
            pdf=ensure_report_pdf(folder)
            if pdf is None:return
            review,count=validate_alpha13_review(folder,pdf)
            plant=load_report_folder(folder)['plant_id'].removeprefix('CI::')
        except (ValueError,OSError,KeyError) as ex:
            show_error('Impossibile aggiornare Excel',ex);return
        ok=messagebox.askyesno('Rigenera Excel con conferme',
            f'{count} associazioni TR–inverter sono state confermate VISIVAMENTE.\n\n'
            'Il programma creera un NUOVO report, senza sovrascrivere quello esistente.\n'
            'Non correggera automaticamente le righe segnalate come Da correggere, '\
            'ne dimostrera la continuita elettrica.\n\nProcedere?',default=messagebox.NO,parent=root)
        if ok:start_engine(pdf,plant,review)

    def make_portfolio():
        try:
            file,count=write_portfolio_csv(project_root)
        except (OSError,ValueError) as ex:
            show_error('Riepilogo non generato',ex);return
        log(f'Riepilogo prove: {count} elaborazioni | {file}')
        if count==0:
            messagebox.showinfo('Nessuna prova','Non ci sono ancora elaborazioni.\nAnalizza un PDF per iniziare.',parent=root)
        else:
            messagebox.showinfo('Riepilogo creato',f'Elaborazioni elencate: {count}\n\nFile CSV:\n{file}\n\n'
                'Le quantita sono risultati documentali, NON percentuali di accuratezza.',parent=root)
            if sys.platform=='win32':
                try:os.startfile(str(file))
                except OSError:pass

    b1=ttk.Button(actions,text='1   Analizza SLD (selezione automatica metodo)',style='Action.TButton',command=analyze)
    b2=ttk.Button(actions,text='2   Verifica visivamente',style='Action.TButton',command=visual_review)
    b3=ttk.Button(actions,text='3   Rigenera Excel con conferme HITL',style='Action.TButton',command=regenerate)
    b4=ttk.Button(actions,text='Riepilogo prove su piu SLD',style='Action.TButton',command=make_portfolio)
    for pos,b in enumerate((b1,b2,b3,b4)):
        b.grid(row=pos//2,column=pos%2,sticky='ew',padx=5,pady=5)
        buttons.append(b)
    for b in (b_pdf,b_report):buttons.append(b)
    ttk.Label(main_frame,text='Motori etichette + candidati inverter dai vettori CAD; nessuna promozione SAP senza evidenza.',
              style='Sub.TLabel',wraplength=830).pack(anchor='w',pady=(0,9))

    status=ttk.Label(main_frame,textvariable=status_var,foreground='#175a39',font=('Segoe UI',10,'bold'))
    status.pack(anchor='w',pady=(0,8))
    display=ttk.LabelFrame(main_frame,text='Messaggi elaborazione',padding=6)
    display.pack(fill='both',expand=True)
    console=tk.Text(display,height=11,wrap='word',font=('Consolas',9),background='#f7f9fa',state='disabled')
    console.pack(side='left',fill='both',expand=True)
    scroll=ttk.Scrollbar(display,command=console.yview)
    scroll.pack(side='right',fill='y');console.configure(yscrollcommand=scroll.set)
    log('Seleziona un PDF. CAD senza testo: QPS documentali; gerarchia CU/TR solo su review specifica del PDF.')

    def poll_events():
        try:
            while True:
                event=events.get_nowait()
                if event[0]=='line':log(event[1])
                elif event[0]=='error':
                    set_busy(False);show_error('Motore non avviato',event[1])
                elif event[0]=='finished':
                    _,code,destination,pdf,mode=event
                    set_busy(False)
                    if code==0 and mode=='alpha21-cad' and (destination/'alpha21_diagnostica_qps.json').is_file():
                        active['report']=None
                        report_var.set('Alpha22: QPS e sbarra CAD; parent CU/TR solo con review PDF-specifica')
                        data=json.loads((destination/'alpha21_diagnostica_qps.json').read_text(encoding='utf8'))
                        summary=data['summary']
                        checked=(destination/'alpha21_gerarchie_stereotipi.xlsx').is_file()
                        log(f'[ALPHA21 CAD] Gruppi QPS completi={summary["qps_groups_complete"]}, '
                            f'QPS documentati={summary["qps_documented_total"]}, '
                            f'String Box mappate con conferma operatore={summary["string_boxes_operator_semantics_resolved"]}')
                        message=(f'Gruppi QPS con sequenza completa: {summary["qps_groups_complete"]}\n'
                          f'QPS identificati nel PDF: {summary["qps_documented_total"]}\n\n')
                        if checked:
                            message += ('Excel CU–TR–INV–STR_Box generato con conferma tecnica OPERATORE.\n'
                                        'Le connessioni TR–INV NON sono state verificate automaticamente.\n')
                        else:
                            message += ('Nessuna review valida applicata: NUMERI SAP e gerarchia non confermati.\n'
                                        'Creato soltanto il registro QPS e le evidenze CAD.\n')
                        message += '\nRisultati in:\n'+str(destination)
                        messagebox.showinfo('CAD Alpha22 — esito documentale',message,parent=root)
                        if sys.platform=='win32':
                            try:os.startfile(str(destination))
                            except OSError:pass
                    elif code==0 and mode in ('alpha15-indexed','alpha16-lvl') and (
                        destination/('alpha16_diagnostica.json' if mode=='alpha16-lvl' else 'alpha15_diagnostica.json')).is_file():
                        active['pdf']=pdf
                        active['report']=None  # Alpha13 visual verifier is for Alpha12 only
                        pdf_var.set(str(pdf))
                        report_var.set('Tag indicizzati: verifica nel foglio Evidenze; visualizzatore non ancora compatibile')
                        diagnostic_name='alpha16_diagnostica.json' if mode=='alpha16-lvl' else 'alpha15_diagnostica.json'
                        data=json.loads((destination/diagnostic_name).read_text(encoding='utf8'))
                        summary=data['summary'];n=summary['inverters']
                        log(f'[RISULTATO {mode}] CU={summary["cu"]}, TR={summary["tr_candidate"]}, '
                            f'INV={n}, SB complete={summary["box_quantities_complete"]}/{n}')
                        if not n:
                            messagebox.showwarning('Non riconosciuto',
                                'Il documento non contiene identificativi compatibili. Nessun asset riconosciuto.',parent=root)
                        else:
                            messagebox.showinfo('Analisi multistile completata',
                                f'Inverter identificati: {n}\n'
                                f'Sequenze String Box complete: {summary["box_quantities_complete"]}/{n}\n\n'
                                'Associazioni TR-inverter soltanto candidate.\n'
                                'La verifica visiva Alpha13 non e ancora compatibile con questo stile.\n\n'
                                'Excel, CSV ed Evidenze in:\n'+str(destination),parent=root)
                        if sys.platform=='win32':
                            try:os.startfile(str(destination))
                            except OSError:pass
                    elif code==0 and (destination/REPORT_NAME).is_file():
                        document=json.loads((destination/REPORT_NAME).read_text(encoding='utf-8'))
                        if document.get('summary',{}).get('inverters',0)==0:
                            active['pdf']=pdf
                            active['report']=None
                            pdf_var.set(str(pdf))
                            report_var.set('SLD senza inverter riconosciuti; metodo non applicabile')
                            log('[NON RICONOSCIUTO] Nessun inverter identificato: non usare questo Excel come gerarchia.')
                            messagebox.showwarning('Riconoscimento insufficiente',
                                'Questo SLD non e stato interpretato dal motore disponibile.\n'
                                'Il report contiene zero inverter e NON costituisce un risultato valido.\n'
                                'Serve un ulteriore metodo di lettura (multistile / OCR / geometria).',parent=root)
                            continue
                        active['pdf']=pdf
                        active['report']=destination
                        report_var.set(str(destination))
                        pdf_var.set(str(pdf))
                        log('[OK] Excel e CSV creati. Seleziona Verifica visivamente per controllarli.')
                        messagebox.showinfo('Elaborazione conclusa',
                            'Excel e CSV generati correttamente.\n\n'
                            'Puoi aprire il report con Verifica visivamente, oppure '\
                            'analizzare un altro SLD.\n\nCartella:\n'+str(destination),parent=root)
                        if sys.platform=='win32':
                            if messagebox.askyesno('Apri risultati','Aprire la cartella dei risultati?',parent=root):
                                try:os.startfile(str(destination))
                                except OSError as ex:log(str(ex))
                    else:
                        log(f'[ERRORE] Codice uscita {code}; controlla i messaggi precedenti.')
                        show_error('Elaborazione incompleta','Il motore non ha prodotto un report valido.\n'+
                                   'Controlla i messaggi nella finestra principale.')
        except queue.Empty:pass
        root.after(125,poll_events)
    root.after(125,poll_events)
    root.mainloop()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
