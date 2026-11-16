"""Interfaccia operatore semplificata — dev14.

Principio: l'operatore vede UNA sola richiesta per volta e solo i controlli
necessari a quella richiesta. Le liste tecniche, i pattern e i bridge avanzati
restano nel backend e non sono esposti nel flusso normale.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pymupdf as fitz

from .operator_interaction import validate_feedback
from .operator_visual import pdf_rect_to_rotated_page
from .feeder_operator_patterns import (
    derive_xfr_binding_value,
    derive_feeder_root_value,
    derive_breakpoint_review_value,
    line_anchor_style,
)
from .operator_feeder import (
    MODE_ROOT,
    MODE_XFR,
    MODE_BREAKPOINT_REVIEW,
    _xfr_index,
    _line_anchor_index,
    _read_feedback,
    _write_feedback,
)

try:
    import tkinter as tk
    from tkinter import ttk, messagebox
except Exception:  # pragma: no cover
    tk = None; ttk = None; messagebox = None


def _load(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _has_action(rows: List[Dict[str, Any]], action: str) -> bool:
    return any((r.get("value", {}) or {}).get("action") == action for r in rows)


def _feedback_key(rec: Dict[str, Any]):
    val = rec.get("value", {}) or {}
    action = val.get("action")
    feeder_id = str(val.get("feeder_id") or "")
    if action == MODE_XFR:
        return action, feeder_id, str(val.get("xfr_instance_key") or "")
    if action == MODE_ROOT:
        return action, feeder_id
    if action == MODE_BREAKPOINT_REVIEW:
        return action, feeder_id, int(val.get("page") or 0), val.get("source_node_id"), val.get("target_node_id")
    return None


def _upsert(rows: List[Dict[str, Any]], rec: Dict[str, Any]) -> List[Dict[str, Any]]:
    key = _feedback_key(rec)
    if key is None:
        return [*rows, rec]
    out: List[Dict[str, Any]] = []
    replaced = False
    for old in rows:
        if _feedback_key(old) == key:
            if not replaced:
                out.append(rec); replaced = True
        else:
            out.append(old)
    if not replaced:
        out.append(rec)
    return out


def _reviewed_breakpoints(rows: List[Dict[str, Any]]) -> set:
    out = set()
    for r in rows:
        v = r.get("value", {}) or {}
        if v.get("action") != MODE_BREAKPOINT_REVIEW:
            continue
        out.add((str(v.get("feeder_id") or ""), int(v.get("page") or 0), v.get("source_node_id"), v.get("target_node_id")))
    return out


def choose_next_task(analysis: Dict[str, Any], feedback: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Restituisce una sola richiesta operatore, in ordine di priorità."""
    reqs = list(analysis.get("feeder_verification_requests", []) or [])
    req = next((r for r in reqs if r.get("status", "OPEN") == "OPEN"), None)
    if not req:
        req = next((r for r in (analysis.get("feeder_verification", {}) or {}).get("resolution_requests", []) or [] if r.get("status", "OPEN") == "OPEN"), None)
    if not req:
        return None
    feeders = list((req.get("context") or {}).get("feeders", []) or [])
    if not feeders:
        return None

    # Una sola calibrazione plant-scoped di base è sufficiente: il backend la
    # propaga sulle istanze compatibili e mantiene la provenienza.
    if not _has_action(feedback, MODE_ROOT):
        f = feeders[0]
        return {"kind": MODE_ROOT, "request": req, "feeder": f}
    if not _has_action(feedback, MODE_XFR):
        f = feeders[0]
        return {"kind": MODE_XFR, "request": req, "feeder": f}

    # dev14c: old UNRESOLVED reviews were recorded before the GUI could express
    # "this is not an electrical element at all". Re-offer each legacy
    # unresolved breakpoint once so the operator can classify boundaries / area
    # boxes / annotations explicitly. New schema-v2 UNRESOLVED decisions remain
    # final and are not looped.
    feeder_by_id = {str(f.get("feeder_id") or ""): f for f in feeders}
    for rec in feedback:
        v = rec.get("value", {}) or {}
        if v.get("action") != MODE_BREAKPOINT_REVIEW:
            continue
        if str(v.get("classification") or "").upper() != "UNRESOLVED":
            continue
        if int(v.get("classification_schema_version") or 1) >= 2:
            continue
        fid = str(v.get("feeder_id") or "")
        f = feeder_by_id.get(fid)
        if f is not None:
            return {"kind": MODE_BREAKPOINT_REVIEW, "request": req, "feeder": f, "breakpoint": dict(v), "revisit_reason": "LEGACY_UNRESOLVED_WITH_NEW_GRAPHIC_OPTION"}

    reviewed = _reviewed_breakpoints(feedback)
    fv = analysis.get("feeder_verification", {}) or {}
    traces = list(fv.get("feeder_traces", []) or [])
    by_id = {str(t.get("feeder_id") or ""): t for t in traces}
    for f in feeders:
        feeder_id = str(f.get("feeder_id") or "")
        trace = by_id.get(feeder_id, {})
        bps = list(trace.get("suggested_breakpoints", []) or []) or list(f.get("suggested_breakpoints", []) or [])
        for bp in bps:
            key = (feeder_id, int(bp.get("page") or 0), bp.get("source_node_id"), bp.get("target_node_id"))
            if key not in reviewed:
                return {"kind": MODE_BREAKPOINT_REVIEW, "request": req, "feeder": f, "breakpoint": bp}
    return None


class SimpleOperatorApp:
    """Wizard minimale: una richiesta, una decisione, nessun comando tecnico."""
    def __init__(self, sld_pdf: str, analysis_path: str, feedback_path: str):
        if tk is None:
            raise RuntimeError("Tkinter non è disponibile")
        self.pdf_path = Path(sld_pdf)
        self.analysis_path = Path(analysis_path)
        self.feedback_path = Path(feedback_path)
        self.analysis = _load(self.analysis_path)
        self.feedback = _read_feedback(self.feedback_path)
        self.task = choose_next_task(self.analysis, self.feedback)
        if not self.task:
            raise ValueError("Nessuna richiesta operatore aperta")
        self.req = self.task["request"]
        self.feeder = self.task["feeder"]
        self.kind = self.task["kind"]
        self.plant_id = (self.analysis.get("plant", {}) or {}).get("plant_id")
        self.doc = fitz.open(self.pdf_path)
        self.xfr = _xfr_index(self.analysis)
        self.line_anchors = _line_anchor_index(self.analysis)
        self.current_page = 1
        self.zoom = 1.0
        self.fit_zoom = 1.0
        self.image = None
        self.click: Optional[List[float]] = None
        self.saved = False

        self.root = tk.Tk()
        self.root.title("Electrical SLD Interpreter — richiesta operatore")
        sw = max(int(self.root.winfo_screenwidth()), 900)
        sh = max(int(self.root.winfo_screenheight()), 650)
        self.root.geometry(f"{min(1450, sw-70)}x{min(900, sh-120)}")
        self.root.minsize(900, 620)

        self.decision = tk.StringVar(master=self.root, value="")
        self.device_display = tk.StringVar(master=self.root, value="Non determinato")
        self.status_text = tk.StringVar(master=self.root, value="")
        self._build()
        self._focus_task()

    def _summary_line(self) -> str:
        tc = self.analysis.get("target_counts", {}) or {}
        fv = (self.analysis.get("feeder_verification", {}) or {}).get("summary", {}) or {}
        return (
            f"Impianto: {self.plant_id}   |   CU {tc.get('conversion_units', 0)}   |   "
            f"CU assegnate ai feeder {fv.get('explicit_schedule_membership_count', 0)}   |   "
            f"verificate dal grafo {fv.get('graph_verified_cu_mv_membership_count', 0)}"
        )

    def _build(self):
        top = ttk.Frame(self.root, padding=(14, 10))
        top.pack(fill=tk.X)
        ttk.Label(top, text="Cosa devi fare adesso", font=("TkDefaultFont", 15, "bold")).pack(anchor="w")
        ttk.Label(top, text=self._summary_line()).pack(anchor="w", pady=(3, 0))

        body = ttk.Panedwindow(self.root, orient=tk.HORIZONTAL)
        body.pack(fill=tk.BOTH, expand=True)
        left = ttk.Frame(body, width=430, padding=14)
        right = ttk.Frame(body)
        body.add(left, weight=0); body.add(right, weight=1)

        self.task_title = ttk.Label(left, text="", font=("TkDefaultFont", 12, "bold"), wraplength=390, justify="left")
        self.task_title.pack(anchor="w", fill=tk.X, pady=(0, 8))
        self.task_help = ttk.Label(left, text="", wraplength=390, justify="left")
        self.task_help.pack(anchor="w", fill=tk.X, pady=(0, 12))

        self.click_frame = ttk.Frame(left)
        self.click_hint = ttk.Label(self.click_frame, text="", wraplength=390, justify="left")
        self.click_hint.pack(anchor="w", pady=(0, 8))
        self.confirm_btn = ttk.Button(self.click_frame, text="Conferma il punto selezionato", command=self._save)
        self.confirm_btn.pack(fill=tk.X, pady=(4, 0))

        self.break_frame = ttk.LabelFrame(left, text="La linea si interrompe qui: cosa vedi?", padding=10)
        ttk.Radiobutton(self.break_frame, text="A e B sono lo stesso collegamento elettrico", variable=self.decision, value="CONDUCTIVE_CONTINUITY").pack(anchor="w", pady=2)
        ttk.Radiobutton(self.break_frame, text="Tra A e B c'è un dispositivo elettrico", variable=self.decision, value="INTERPOSED_DEVICE").pack(anchor="w", pady=2)
        ttk.Radiobutton(self.break_frame, text="A e B appartengono a un elemento grafico NON elettrico (bordo / area / annotazione)", variable=self.decision, value="NON_ELECTRICAL_GRAPHIC").pack(anchor="w", pady=2)
        ttk.Radiobutton(self.break_frame, text="Non sono in grado di stabilirlo", variable=self.decision, value="UNRESOLVED").pack(anchor="w", pady=2)
        ttk.Label(self.break_frame, text="Se c'è un dispositivo, indica il tipo solo se ti è chiaro:").pack(anchor="w", pady=(10, 2))
        self.device_combo = ttk.Combobox(self.break_frame, textvariable=self.device_display, state="readonly", values=[
            "Non determinato",
            "Cabina di sezionamento / Sectionalizing cabinet",
            "Sezionatore / Interruttore di manovra",
            "Interruttore automatico / Circuit breaker",
            "Trasformatore",
            "Altro dispositivo elettrico",
        ])
        self.device_combo.pack(fill=tk.X)
        ttk.Button(self.break_frame, text="Registra questa valutazione", command=self._save).pack(fill=tk.X, pady=(12, 0))

        ttk.Separator(left, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=14)
        ttk.Label(left, textvariable=self.status_text, wraplength=390, justify="left").pack(anchor="w", fill=tk.X)
        ttk.Button(left, text="Esci e riprendi in seguito", command=self.root.destroy).pack(fill=tk.X, pady=(16, 0))
        ttk.Button(left, text="Mostra dettagli tecnici", command=self._show_details).pack(fill=tk.X, pady=(6, 0))

        self.canvas = tk.Canvas(right, background="white", cursor="cross")
        xb = ttk.Scrollbar(right, orient=tk.HORIZONTAL, command=self.canvas.xview)
        yb = ttk.Scrollbar(right, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=xb.set, yscrollcommand=yb.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        yb.grid(row=0, column=1, sticky="ns"); xb.grid(row=1, column=0, sticky="ew")
        right.rowconfigure(0, weight=1); right.columnconfigure(0, weight=1)
        self.canvas.bind("<Button-1>", self._on_click)
        self.canvas.bind("<Control-MouseWheel>", self._mouse_zoom)

        if self.kind == MODE_BREAKPOINT_REVIEW:
            self.break_frame.pack(fill=tk.X)
            self.task_title.config(text="Verifica un punto in cui il percorso elettrico si interrompe")
            self.task_help.config(text=(
                f"Feeder {self.feeder.get('feeder_id')}. Il software ha trovato due estremi A e B molto vicini, "
                "ma non può decidere da solo se siano lo stesso conduttore, se tra loro ci sia un dispositivo, "
                "oppure se stia osservando un elemento grafico non elettrico (per esempio il bordo di un'area). "
                "NON cliccare sul disegno: guarda A e B e scegli una delle quattro opzioni qui sotto."
            ))
            self.status_text.set("Nessuna modifica viene applicata finché non registri una delle quattro valutazioni.")
        else:
            self.click_frame.pack(fill=tk.X)
            if self.kind == MODE_ROOT:
                self.task_title.config(text=f"1 di 2 — Indica l'origine elettrica del feeder {self.feeder.get('feeder_id')}")
                self.task_help.config(text=(
                    "Clicca sul conduttore nel punto da cui parte il feeder: secondario del TR HV/MV se rappresentato; "
                    "altrimenti sbarra MT o uscita del breaker. Non cliccare sulla scritta del feeder."
                ))
                self.click_hint.config(text="Dopo il clic comparirà un punto blu. Se è corretto, premi «Conferma il punto selezionato».")
            else:
                k = self._first_xfr_key()
                self.task_title.config(text=f"2 di 2 — Indica il terminale MT di XFR_{k}")
                self.task_help.config(text=(
                    "Clicca sul punto in cui il trasformatore è collegato alla rete MT. Non cliccare dentro il simbolo e non attraversare gli avvolgimenti."
                ))
                self.click_hint.config(text="Dopo il clic comparirà un punto blu. Se è corretto, premi «Conferma il punto selezionato».")
            self.status_text.set("In attesa della tua selezione sul disegno.")

    def _first_xfr_key(self) -> Optional[str]:
        members = [str(x) for x in self.feeder.get("member_cu_instance_keys", []) or []]
        return members[0] if members else (sorted(self.xfr.keys(), key=lambda x: int(x) if x.isdigit() else x)[0] if self.xfr else None)

    def _root_rep(self):
        line = str(self.feeder.get("feeder_id") or "")
        reps = self.line_anchors.get(line, [])
        reps = sorted(reps, key=lambda r: (0 if r.get("style") == "DELIMITED" else 1, -r.get("bbox", [0,0,0,0])[1]))
        return reps[0] if reps else None

    def _focus_task(self):
        if self.kind == MODE_ROOT:
            r = self._root_rep()
            if not r:
                self.status_text.set("Il programma non trova un riferimento grafico valido per questo feeder. Esci e segnala il caso.")
                return
            self._show_page(r["page"], fit=True)
            self.root.after(30, lambda: self._center_bbox(r["bbox"]))
        elif self.kind == MODE_XFR:
            k = self._first_xfr_key(); reps = self.xfr.get(str(k), []) if k is not None else []
            if not reps:
                self.status_text.set("Il programma non trova il trasformatore rappresentativo. Esci e segnala il caso.")
                return
            r = reps[0]; self._show_page(r["page"], fit=True); self.root.after(30, lambda: self._center_bbox(r["bbox"]))
        else:
            bp = self.task.get("breakpoint") or {}
            self._show_page(bp.get("page", 1), fit=True)
            self.root.after(30, lambda: self._center_points(bp.get("point_a"), bp.get("point_b")))

    def _show_page(self, page_no: int, fit=False):
        self.current_page = max(1, min(int(page_no), self.doc.page_count))
        page = self.doc[self.current_page - 1]
        self.root.update_idletasks()
        if fit:
            cw = max(self.canvas.winfo_width() - 30, 300); ch = max(self.canvas.winfo_height() - 30, 300)
            self.fit_zoom = max(.12, min(cw/max(page.rect.width,1), ch/max(page.rect.height,1)))
            self.zoom = self.fit_zoom
        self._render()

    def _render(self):
        page = self.doc[self.current_page - 1]
        pix = page.get_pixmap(matrix=fitz.Matrix(self.zoom, self.zoom), alpha=False)
        enc = base64.b64encode(pix.tobytes("png")).decode("ascii")
        self.image = tk.PhotoImage(data=enc)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, image=self.image, anchor="nw")
        self.canvas.configure(scrollregion=(0,0,pix.width,pix.height))

        if self.kind == MODE_ROOT:
            r = self._root_rep(); reps = [r] if r else []
        elif self.kind == MODE_XFR:
            k = self._first_xfr_key(); reps = self.xfr.get(str(k), []) if k else []
        else:
            reps = []
        for r in reps:
            if int(r["page"]) != self.current_page: continue
            rr = pdf_rect_to_rotated_page(page, r["bbox"])
            self.canvas.create_rectangle(rr.x0*self.zoom, rr.y0*self.zoom, rr.x1*self.zoom, rr.y1*self.zoom, outline="#d97706", width=3)

        if self.kind == MODE_BREAKPOINT_REVIEW:
            bp = self.task.get("breakpoint") or {}
            if int(bp.get("page", 0)) == self.current_page:
                for label, pt in (("A", bp.get("point_a")), ("B", bp.get("point_b"))):
                    if pt:
                        self.canvas.create_oval(pt[0]*self.zoom-8, pt[1]*self.zoom-8, pt[0]*self.zoom+8, pt[1]*self.zoom+8, outline="#dc2626", width=3)
                        self.canvas.create_text(pt[0]*self.zoom+12, pt[1]*self.zoom, text=label, anchor="w", font=("TkDefaultFont", 11, "bold"))
        elif self.click:
            p = self.click
            self.canvas.create_oval(p[0]*self.zoom-6,p[1]*self.zoom-6,p[0]*self.zoom+6,p[1]*self.zoom+6,outline="#2563eb",width=3)

    def _center_bbox(self, bbox):
        page = self.doc[self.current_page - 1]
        rr = pdf_rect_to_rotated_page(page, bbox)
        cw=max(self.canvas.winfo_width()-30,300); ch=max(self.canvas.winfo_height()-30,300)
        desired=max(self.fit_zoom,min(min(cw/max(rr.width*8,160),ch/max(rr.height*8,160)),5.0))
        if abs(desired-self.zoom)>.02:
            self.zoom=desired; self._render(); rr=pdf_rect_to_rotated_page(page,bbox)
        px=(rr.x0+rr.x1)/2*self.zoom; py=(rr.y0+rr.y1)/2*self.zoom
        allb=self.canvas.bbox("all") or (0,0,1,1); tw=max(float(allb[2]),1); th=max(float(allb[3]),1)
        self.canvas.xview_moveto(max(0,min(1,(px-cw/2)/tw))); self.canvas.yview_moveto(max(0,min(1,(py-ch/2)/th)))

    def _center_points(self, a, b):
        if not a or not b: return
        self._center_bbox([min(a[0],b[0])-20,min(a[1],b[1])-20,max(a[0],b[0])+20,max(a[1],b[1])+20])

    def _mouse_zoom(self, event):
        self.zoom=max(.08,min(8.0,self.zoom*(1.2 if event.delta>0 else 1/1.2))); self._render()

    def _on_click(self, event):
        if self.kind == MODE_BREAKPOINT_REVIEW:
            self.status_text.set("Per questo controllo non devi cliccare sul disegno: scegli una delle tre valutazioni a sinistra.")
            return
        x=self.canvas.canvasx(event.x)/self.zoom; y=self.canvas.canvasy(event.y)/self.zoom
        page=self.doc[self.current_page-1]; pt=fitz.Point(x,y); pt=pt*page.derotation_matrix if page.rotation else pt
        self.click=[round(pt.x,3),round(pt.y,3)]
        self.status_text.set("Punto blu selezionato. Controlla che sia quello giusto e premi «Conferma il punto selezionato».")
        self._render()

    def _save(self):
        feeder_id=str(self.feeder.get("feeder_id") or "")
        if self.kind in {MODE_ROOT, MODE_XFR} and not self.click:
            messagebox.showwarning("Manca il punto", "Clicca prima sul punto corretto nello schema.")
            return
        if self.kind == MODE_ROOT:
            r=self._root_rep()
            if not r:
                messagebox.showerror("Impossibile salvare", "Non trovo il riferimento grafico del feeder.")
                return
            value=derive_feeder_root_value(r["bbox"],self.click,feeder_id=feeder_id,anchor_text=r.get("text"),page=self.current_page)
        elif self.kind == MODE_XFR:
            k=self._first_xfr_key(); reps=self.xfr.get(str(k),[]) if k is not None else []
            if not reps:
                messagebox.showerror("Impossibile salvare", "Non trovo il trasformatore rappresentativo.")
                return
            value=derive_xfr_binding_value(reps[0]["bbox"],self.click,feeder_id=feeder_id,xfr_instance_key=k,page=self.current_page)
        else:
            bp=self.task.get("breakpoint") or {}
            cls=str(self.decision.get() or "")
            if cls not in {"CONDUCTIVE_CONTINUITY","INTERPOSED_DEVICE","NON_ELECTRICAL_GRAPHIC","UNRESOLVED"}:
                messagebox.showwarning("Manca la valutazione", "Scegli una delle quattro opzioni.")
                return
            display_to_type={
                "Non determinato":"UNDETERMINED",
                "Cabina di sezionamento / Sectionalizing cabinet":"SECTIONALIZING_CABINET",
                "Sezionatore / Interruttore di manovra":"SWITCH_DISCONNECTOR",
                "Interruttore automatico / Circuit breaker":"CIRCUIT_BREAKER",
                "Trasformatore":"TRANSFORMER",
                "Altro dispositivo elettrico":"OTHER_ELECTRICAL_DEVICE",
            }
            value=derive_breakpoint_review_value(bp,classification=cls,device_type=display_to_type.get(self.device_display.get(),"UNDETERMINED"))

        rec={
            "request_id":f"{self.req.get('request_id')}::{self.kind}::SIMPLE",
            "target":"FEEDER_ELECTRICAL_PATH_VERIFICATION",
            "option":"PROVIDE_VALUE",
            "status":"OPERATOR_PROVIDED",
            "plant_id":self.plant_id,
            "doc":self.pdf_path.name,
            "page":self.current_page,
            "learning_scope":"INSTANCE" if self.kind==MODE_BREAKPOINT_REVIEW else "PLANT",
            "value":value,
            "context":{"plant_id":self.plant_id,"interaction_mode":"SIMPLE_GUIDED_IT","analysis_file":self.analysis_path.name},
        }
        rec=validate_feedback(rec)
        self.feedback=_upsert(self.feedback,rec)
        _write_feedback(self.feedback_path,self.feedback)
        self.saved=True
        if self.kind == MODE_ROOT:
            # Passo B nello stesso avvio: non serve ricalcolare il grafo tra A e B.
            self.task={"kind":MODE_XFR,"request":self.req,"feeder":self.feeder}
            self.kind=MODE_XFR; self.click=None
            self.click_frame.pack_forget(); self.break_frame.pack_forget(); self.click_frame.pack(fill=tk.X)
            k=self._first_xfr_key()
            self.task_title.config(text=f"2 di 2 — Indica il terminale MT di XFR_{k}")
            self.task_help.config(text="Clicca sul punto in cui il trasformatore è collegato alla rete MT. Non cliccare dentro il simbolo.")
            self.click_hint.config(text="Dopo il clic comparirà un punto blu. Se è corretto, premi «Conferma il punto selezionato».")
            self.status_text.set("PASSO 1 salvato. Ora completa il PASSO 2.")
            self._focus_task()
            return
        messagebox.showinfo("Informazione salvata", "Registrazione completata. Il programma aggiornerà automaticamente l'analisi dopo la chiusura.")
        self.root.destroy()

    def _show_details(self):
        fvid=(self.feeder.get("feeder_id") or "")
        bp=self.task.get("breakpoint") or {}
        txt=(f"Tipo richiesta: {self.kind}\nFeeder: {fvid}\nPagina: {bp.get('page', self.current_page)}\n"
             f"File analisi: {self.analysis_path.name}\nFile feedback: {self.feedback_path.name}")
        messagebox.showinfo("Dettagli tecnici", txt)

    def run(self) -> bool:
        self.root.mainloop()
        return self.saved
