"""Interfaccia grafica guidata per la calibrazione dei percorsi feeder — dev13.

La GUI NON serve per assegnare manualmente le CU ai feeder. Le membership già
ricavate dal documento rimangono responsabilità del motore. L'operatore fornisce
solo due calibrazioni grafiche di base:
  1) origine elettrica del feeder sullo SLD;
  2) terminale MT di un trasformatore XFR rappresentativo.

Le azioni di bridge restano disponibili, ma sono volutamente separate e marcate
come avanzate perché devono essere usate solo quando il motore segnala un punto
di interruzione da confermare.
"""
from __future__ import annotations

import argparse, base64, json
from pathlib import Path
from typing import Any, Dict, List

import pymupdf as fitz

from .operator_interaction import validate_feedback
from .operator_visual import pdf_rect_to_rotated_page
from .feeder_operator_patterns import (
    derive_xfr_binding_value,
    derive_feeder_root_value,
    derive_instance_bridge_value,
    derive_bridge_value,
    derive_breakpoint_review_value,
    line_anchor_style,
)

try:
    import tkinter as tk
    from tkinter import ttk, messagebox
except Exception:  # pragma: no cover
    tk = None; ttk = None; messagebox = None


def _load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _read_feedback(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    obj = _load(path)
    if isinstance(obj, list):
        return obj
    return list(obj.get("operator_feedback", obj.get("records", [])) or [])


def _write_feedback(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"operator_feedback": rows}, ensure_ascii=False, indent=2), encoding="utf-8")


def _xfr_index(analysis: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    out: Dict[str, List[Dict[str, Any]]] = {}
    for p in analysis.get("pages", []) or []:
        for a in p.get("text_equipment_anchors", []) or []:
            attrs = a.get("attributes", {}) or {}
            key = attrs.get("xfr_instance_hint")
            if a.get("evidence_kind") != "XFR_TAG" or key is None or not a.get("bbox"):
                continue
            out.setdefault(str(key), []).append({
                "page": int(p.get("page") or 1),
                "bbox": a["bbox"],
                "text": a.get("text") or a.get("tag") or f"XFR_{key}",
            })
    return out


def _line_anchor_index(analysis: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    out: Dict[str, List[Dict[str, Any]]] = {}
    import re
    exact = re.compile(r"^MV\s*[-_]?\s*\d{1,3}$", re.I)
    for p in analysis.get("pages", []) or []:
        for a in p.get("layout_mv_line_anchors", []) or []:
            line = a.get("line_instance_hint")
            raw = " ".join(str(a.get("text") or "").strip().split())
            if a.get("anchor_role") != "INSTANCE" or not line or not a.get("bbox") or not exact.fullmatch(raw):
                continue
            out.setdefault(str(line), []).append({
                "page": int(p.get("page") or 1),
                "bbox": a["bbox"],
                "text": raw,
                "style": line_anchor_style(raw),
            })
    return out


MODE_ROOT = "BIND_FEEDER_ROOT_PATTERN"
MODE_XFR = "BIND_XFR_MV_TERMINAL_PATTERN"
MODE_BRIDGE_INSTANCE = "ADD_FEEDER_GRAPH_BRIDGE_INSTANCE"  # legacy/backward compatibility
MODE_BRIDGE_PATTERN = "ADD_CONDUCTIVE_GAP_BRIDGE_PATTERN"
MODE_BREAKPOINT_REVIEW = "CLASSIFY_FEEDER_BREAKPOINT"


def _status_it(status: Any) -> str:
    mapping = {
        "GRAPH_VERIFIED": "VERIFICATO DAL GRAFO",
        "PARTIALLY_GRAPH_VERIFIED": "PARZIALMENTE VERIFICATO",
        "SOURCE_CROSSCHECKED_NOT_GRAPH_VERIFIED": "RISCONTRATO NELLE FONTI, NON VERIFICATO DAL GRAFO",
        "MEMBERSHIP_SOURCE_EXPLICIT_TRACE_UNRESOLVED": "APPARTENENZA ESPLICITA, PERCORSO NON RISOLTO",
    }
    return mapping.get(str(status or ""), str(status or ""))


class FeederCalibrationApp:
    def __init__(self, sld_pdf: str, analysis_path: str, feedback_path: str):
        if tk is None:
            raise RuntimeError("Tkinter non è disponibile")
        self.pdf_path = Path(sld_pdf)
        self.analysis_path = Path(analysis_path)
        self.feedback_path = Path(feedback_path)
        self.analysis = _load(self.analysis_path)
        self.doc = fitz.open(self.pdf_path)
        self.feedback = _read_feedback(self.feedback_path)
        self.req = next((r for r in self.analysis.get("feeder_verification_requests", []) or [] if r.get("status", "OPEN") == "OPEN"), None)
        if not self.req:
            self.req = next((r for r in (self.analysis.get("feeder_verification", {}) or {}).get("resolution_requests", []) or [] if r.get("status", "OPEN") == "OPEN"), None)
        if not self.req:
            raise ValueError("Nessuna richiesta aperta di verifica feeder trovata")
        self.plant_id = (self.analysis.get("plant", {}) or {}).get("plant_id")
        self.feeders = list((self.req.get("context") or {}).get("feeders", []) or [])
        self.xfr = _xfr_index(self.analysis)
        self.line_anchors = _line_anchor_index(self.analysis)
        self.current_page = 1
        self.zoom = 1.0
        self.fit_zoom = 1.0
        self.image = None
        self.clicks: List[List[float]] = []

        # Tkinter richiede che la finestra root esista prima di creare
        # StringVar/IntVar/etc. La dev11b creava self.mode troppo presto e
        # falliva all'avvio con: "Too early to create variable".
        self.root = tk.Tk()
        # Il primo passo corretto è sempre l'origine feeder.
        self.mode = tk.StringVar(master=self.root, value=MODE_ROOT)
        self.breakpoint_decision = tk.StringVar(master=self.root, value="")
        self.breakpoint_device_display = tk.StringVar(master=self.root, value="Non determinato")

        self.root.title("Electrical SLD Interpreter — Calibrazione guidata feeder")
        # Dimensionamento adattivo: le versioni precedenti usavano 1580x940
        # fisso e, con scaling DPI / taskbar, i comandi inferiori potevano
        # finire fuori dall'area realmente visibile.
        sw = max(int(self.root.winfo_screenwidth()), 800)
        sh = max(int(self.root.winfo_screenheight()), 600)
        ww = min(1500, max(900, sw - 80))
        wh = min(880, max(620, sh - 140))
        self.root.geometry(f"{ww}x{wh}")
        self.root.minsize(900, 620)
        self._build()
        # Scorciatoie di sicurezza: dopo aver selezionato il punto, Invio o
        # Ctrl+S equivalgono al pulsante di conferma visibile nella procedura.
        self.root.bind("<Return>", lambda _e: self._save())
        self.root.bind("<Control-s>", lambda _e: self._save())
        self._load_feeder(0)
        self._refresh_progress()

    def _build(self):
        header = ttk.Frame(self.root, padding=(10, 8))
        header.pack(fill=tk.X)
        ttk.Label(header, text="Calibrazione guidata del percorso elettrico", font=("TkDefaultFont", 13, "bold")).pack(anchor="w")
        ttk.Label(
            header,
            text=(
                "Scopo: insegnare al motore dove agganciarsi al grafo elettrico. "
                "NON stai assegnando manualmente le CU ai feeder: quelle appartenenze sono già ricavate dal documento."
            ),
            wraplength=1450,
        ).pack(anchor="w", pady=(3, 0))

        body = ttk.Panedwindow(self.root, orient=tk.HORIZONTAL)
        body.pack(fill=tk.BOTH, expand=True)

        # Colonna sinistra: area comandi verticalmente scorrevole + barra azioni
        # sempre visibile in basso. In dev11c i controlli inferiori potevano
        # finire fuori schermo su display con altezza utile ridotta / scaling DPI.
        left_shell = ttk.Frame(body, width=470)
        center = ttk.Frame(body)
        body.add(left_shell, weight=0)
        body.add(center, weight=1)

        left_shell.rowconfigure(0, weight=1)
        left_shell.columnconfigure(0, weight=1)

        left_canvas = tk.Canvas(left_shell, highlightthickness=0, width=455)
        left_scroll = ttk.Scrollbar(left_shell, orient=tk.VERTICAL, command=left_canvas.yview)
        left_canvas.configure(yscrollcommand=left_scroll.set)
        left_canvas.grid(row=0, column=0, sticky="nsew")
        left_scroll.grid(row=0, column=1, sticky="ns")

        left = ttk.Frame(left_canvas, padding=10)
        self._left_window = left_canvas.create_window((0, 0), window=left, anchor="nw")
        self.left_canvas = left_canvas

        def _sync_left_scrollregion(_event=None):
            left_canvas.configure(scrollregion=left_canvas.bbox("all"))

        def _sync_left_width(event):
            # Evita una barra orizzontale: il pannello interno segue la larghezza
            # utile del canvas, lasciando visibile la scrollbar verticale.
            left_canvas.itemconfigure(self._left_window, width=max(event.width, 1))

        left.bind("<Configure>", _sync_left_scrollregion)
        left_canvas.bind("<Configure>", _sync_left_width)

        def _left_mousewheel(event):
            # Windows/macOS: la rotella scorre il pannello comandi quando il
            # puntatore è sulla colonna sinistra. Ctrl+rotella resta riservato
            # allo zoom dello schema nel canvas centrale.
            if getattr(event, "state", 0) & 0x0004:
                return
            delta = getattr(event, "delta", 0)
            if delta:
                left_canvas.yview_scroll(int(-delta / 120) or (-1 if delta > 0 else 1), "units")

        for w in (left_canvas, left):
            w.bind("<MouseWheel>", _left_mousewheel, add="+")

        # Barra inferiore non scorrevole: le azioni principali restano sempre
        # raggiungibili, indipendentemente dall'altezza dello schermo.
        footer = ttk.Frame(left_shell, padding=(10, 6, 10, 10))
        footer.grid(row=1, column=0, columnspan=2, sticky="ew")
        footer.columnconfigure(0, weight=1)
        footer.columnconfigure(1, weight=1)
        self.footer_save_button = ttk.Button(footer, text="Conferma passo corrente", command=self._save)
        self.footer_save_button.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 4))
        ttk.Button(footer, text="Annulla selezione", command=self._reset_clicks).grid(row=1, column=0, sticky="ew", padx=(0, 4))
        ttk.Button(footer, text="Chiudi", command=self._close_guided).grid(row=1, column=1, sticky="ew", padx=(4, 0))

        # Passo 1: feeder
        f1 = ttk.LabelFrame(left, text="1. Scegli il feeder da calibrare", padding=7)
        f1.pack(fill=tk.X, pady=(0, 8))
        self.feeder_list = tk.Listbox(f1, exportselection=False, width=52, height=10)
        self.feeder_list.pack(fill=tk.X)
        self.feeder_list.bind("<<ListboxSelect>>", self._on_feeder)
        for f in self.feeders:
            self.feeder_list.insert(tk.END, f"{f.get('feeder_id')} — {len(f.get('member_cu_instance_keys', []))} CU — {_status_it(f.get('status'))}")

        # Passo 2: trasformatore rappresentativo
        f2 = ttk.LabelFrame(left, text="2. Trasformatore rappresentativo del feeder", padding=7)
        f2.pack(fill=tk.X, pady=(0, 8))
        self.xfr_list = tk.Listbox(f2, exportselection=False, width=52, height=9)
        self.xfr_list.pack(fill=tk.X)
        self.xfr_list.bind("<<ListboxSelect>>", self._on_xfr)

        # Procedura guidata
        guide = ttk.LabelFrame(left, text="3. Procedura guidata", padding=8)
        guide.pack(fill=tk.X, pady=(0, 8))
        self.btn_root = ttk.Button(guide, text="A. Indica l'origine elettrica del feeder", command=lambda: self._set_mode(MODE_ROOT))
        self.btn_root.pack(fill=tk.X, pady=2)
        self.btn_xfr = ttk.Button(guide, text="B. Indica il terminale MT del trasformatore", command=lambda: self._set_mode(MODE_XFR))
        self.btn_xfr.pack(fill=tk.X, pady=2)

        # Pulsante principale volutamente collocato QUI, immediatamente sotto
        # i passi A/B: deve rimanere visibile senza scorrere il pannello.
        self.save_button = ttk.Button(guide, text="Conferma e salva PASSO A", command=self._save)
        self.save_button.pack(fill=tk.X, pady=(10, 5))
        ttk.Label(
            guide,
            text="Dopo aver cliccato il punto blu, premi il pulsante qui sopra. In alternativa: Invio oppure Ctrl+S.",
            wraplength=385,
            justify="left",
        ).pack(anchor="w", pady=(0, 6))

        self.instruction = tk.StringVar(value="")
        ttk.Label(guide, textvariable=self.instruction, wraplength=385, justify="left").pack(anchor="w", pady=(8, 4))
        self.selection_status = tk.StringVar(value="Nessun punto selezionato")
        ttk.Label(guide, textvariable=self.selection_status, wraplength=385).pack(anchor="w", pady=(0, 4))

        self.progress = tk.StringVar(value="")
        ttk.Label(left, textvariable=self.progress, wraplength=395, justify="left").pack(anchor="w", pady=(2, 8))

        # Verifica breakpoint: prima si classifica la discontinuità; solo una
        # conferma esplicita di continuità grafica può creare un bridge.
        adv = ttk.LabelFrame(left, text="4. Verifica dei punti di interruzione", padding=8)
        adv.pack(fill=tk.X, pady=(0, 8))
        ttk.Button(adv, text="Esamina il prossimo punto di interruzione", command=lambda: self._set_mode(MODE_BREAKPOINT_REVIEW)).pack(fill=tk.X, pady=2)
        ttk.Label(adv, text="Quando sono visibili A e B, scegli cosa c'è realmente tra i due punti:", wraplength=385, justify="left").pack(anchor="w", pady=(7, 2))
        ttk.Radiobutton(adv, text="È solo una continuità grafica: collega A–B", variable=self.breakpoint_decision, value="CONDUCTIVE_CONTINUITY").pack(anchor="w")
        ttk.Radiobutton(adv, text="C'è un dispositivo elettrico tra A e B", variable=self.breakpoint_decision, value="INTERPOSED_DEVICE").pack(anchor="w")
        ttk.Radiobutton(adv, text="È un elemento grafico NON elettrico (bordo / area / annotazione)", variable=self.breakpoint_decision, value="NON_ELECTRICAL_GRAPHIC").pack(anchor="w")
        ttk.Radiobutton(adv, text="Non riesco a stabilirlo con sicurezza", variable=self.breakpoint_decision, value="UNRESOLVED").pack(anchor="w")
        ttk.Label(adv, text="Se hai indicato un dispositivo, tipo (facoltativo):").pack(anchor="w", pady=(6, 1))
        self.breakpoint_device_combo = ttk.Combobox(adv, textvariable=self.breakpoint_device_display, state="readonly", values=[
            "Non determinato",
            "Cabina di sezionamento / Sectionalizing cabinet",
            "Sezionatore / Interruttore di manovra",
            "Interruttore automatico / Circuit breaker",
            "Trasformatore",
            "Altro dispositivo elettrico",
        ])
        self.breakpoint_device_combo.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(
            adv,
            text=(
                "Regola di sicurezza: un dispositivo interposto NON viene mai bypassato con un ponte. "
                "Se scegli 'continuità grafica', il collegamento vale solo per questo breakpoint esatto."
            ),
            wraplength=385,
            justify="left",
        ).pack(anchor="w", pady=(6, 0))
        ttk.Separator(adv, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=8)
        ttk.Button(adv, text="Avanzato: insegna un gap conduttivo ripetitivo", command=lambda: self._set_mode(MODE_BRIDGE_PATTERN)).pack(fill=tk.X, pady=2)

        self.page_label = ttk.Label(left, text="")
        self.page_label.pack(anchor="w", pady=(4, 12))

        self.canvas = tk.Canvas(center, background="white", cursor="cross")
        xb = ttk.Scrollbar(center, orient=tk.HORIZONTAL, command=self.canvas.xview)
        yb = ttk.Scrollbar(center, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=xb.set, yscrollcommand=yb.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        yb.grid(row=0, column=1, sticky="ns")
        xb.grid(row=1, column=0, sticky="ew")
        center.rowconfigure(0, weight=1)
        center.columnconfigure(0, weight=1)
        self.canvas.bind("<Button-1>", self._click)
        self.canvas.bind("<Control-MouseWheel>", self._mouse_zoom)

        self._update_instruction()
        self._refresh_save_button()

    def _set_mode(self, mode: str):
        feeder_id = str((self._selected_feeder() or {}).get("feeder_id") or "")
        if mode == MODE_XFR and feeder_id and not self._has_saved_action(MODE_ROOT, feeder_id):
            if messagebox:
                messagebox.showwarning(
                    "Completa prima il PASSO A",
                    "Prima di indicare il terminale MT devi confermare e salvare l'origine elettrica del feeder selezionato (PASSO A).",
                )
            self.mode.set(MODE_ROOT)
            self._refresh_save_button()
            self._update_instruction()
            self._focus_root()
            return
        self.mode.set(mode)
        if mode == MODE_BREAKPOINT_REVIEW:
            self.breakpoint_decision.set("")
            self.breakpoint_device_display.set("Non determinato")
        self._refresh_save_button()
        self._reset_clicks()
        self._update_instruction()
        if mode == MODE_ROOT:
            self._focus_root()
        elif mode in {MODE_BRIDGE_INSTANCE, MODE_BREAKPOINT_REVIEW}:
            self._focus_breakpoint()
        else:
            k = self._selected_xfr_key()
            if k:
                self._focus_xfr(k)

    def _update_instruction(self):
        mode = self.mode.get()
        if mode == MODE_ROOT:
            txt = (
                "PASSO A — Il programma evidenzia il riferimento del feeder (es. MV-01). "
                "Clicca sul punto elettrico da cui il feeder parte nello SLD: secondario HV/MV se visibile, altrimenti sbarra MT o breaker di partenza disponibile. "
                "Non cliccare sulla scritta MV-01. Dopo il clic premi «Conferma e salva PASSO A»: solo allora il passo è registrato."
            )
        elif mode == MODE_XFR:
            txt = (
                "PASSO B — Il programma evidenzia il tag XFR selezionato. "
                "Clicca sul punto in cui il trasformatore è connesso alla rete MT del feeder. "
                "Non cliccare dentro il trasformatore e non attraversare gli avvolgimenti. Dopo il clic premi «Conferma e salva PASSO B»."
            )
        elif mode == MODE_BREAKPOINT_REVIEW:
            txt = (
                "VERIFICA BREAKPOINT — Il programma evidenzia A e B. Non cliccare sullo schema: osserva cosa c'è tra i due punti, "
                "scegli una delle tre opzioni nella sezione 4 e poi premi «Registra valutazione del breakpoint». "
                "Un dispositivo reale non viene mai bypassato automaticamente."
            )
        elif mode == MODE_BRIDGE_INSTANCE:
            txt = (
                "MODALITÀ LEGACY — selezione manuale di due estremi per un bridge singolo. "
                "Usare solo per compatibilità con feedback precedenti."
            )
        else:
            txt = (
                "AZIONE AVANZATA — Clicca i due estremi di un gap conduttivo ripetitivo vicino ai terminali XFR. "
                "Usare solo quando il programma ha già individuato lo stesso difetto grafico in più istanze."
            )
        self.instruction.set(txt)

    def _has_saved_action(self, action: str, feeder_id: str | None = None) -> bool:
        feeder_id = str(feeder_id or "")
        for rec in self.feedback:
            val = rec.get("value", {}) or {}
            if val.get("action") != action:
                continue
            if feeder_id and str(val.get("feeder_id") or "") != feeder_id:
                continue
            return True
        return False

    @staticmethod
    def _feedback_identity(rec):
        val = rec.get("value", {}) or {}
        action = val.get("action")
        feeder_id = str(val.get("feeder_id") or "")
        if action == MODE_XFR:
            return (action, feeder_id, str(val.get("xfr_instance_key") or ""))
        if action == MODE_BREAKPOINT_REVIEW:
            return (action, feeder_id, val.get("page"), val.get("source_node_id"), val.get("target_node_id"))
        if action in {MODE_ROOT, MODE_BRIDGE_INSTANCE, MODE_BRIDGE_PATTERN}:
            return (action, feeder_id)
        return None

    def _upsert_feedback(self, rec):
        """Evita duplicati involontari durante la procedura guidata.

        Una nuova calibrazione dello stesso passo/feeder sostituisce quella
        precedente invece di accumulare pattern quasi identici.
        """
        key = self._feedback_identity(rec)
        if key is None:
            self.feedback.append(rec)
            return
        kept = []
        replaced = False
        for old in self.feedback:
            if self._feedback_identity(old) == key:
                if not replaced:
                    kept.append(rec)
                    replaced = True
            else:
                kept.append(old)
        if not replaced:
            kept.append(rec)
        self.feedback = kept

    def _refresh_save_button(self):
        mode = self.mode.get()
        if mode == MODE_ROOT:
            text = "Conferma e salva PASSO A"
        elif mode == MODE_XFR:
            text = "Conferma e salva PASSO B"
        elif mode == MODE_BREAKPOINT_REVIEW:
            text = "Registra valutazione del breakpoint"
        elif mode == MODE_BRIDGE_INSTANCE:
            text = "Conferma il bridge singolo"
        else:
            text = "Conferma il pattern di gap"
        if hasattr(self, "save_button"):
            self.save_button.config(text=text)
        if hasattr(self, "footer_save_button"):
            self.footer_save_button.config(text=text)

    def _refresh_progress(self):
        root_n = 0; xfr_n = 0; bridge_i = 0; bridge_p = 0; bp_n = 0; bp_dev = 0; bp_cont = 0; bp_unc = 0
        for rec in self.feedback:
            val = rec.get("value", {}) or {}
            action = val.get("action")
            if action == MODE_ROOT: root_n += 1
            elif action == MODE_XFR: xfr_n += 1
            elif action == MODE_BRIDGE_INSTANCE: bridge_i += 1
            elif action == MODE_BRIDGE_PATTERN: bridge_p += 1
            elif action == MODE_BREAKPOINT_REVIEW:
                bp_n += 1
                cls = str(val.get("classification") or "")
                if cls == "INTERPOSED_DEVICE": bp_dev += 1
                elif cls == "CONDUCTIVE_CONTINUITY": bp_cont += 1
                elif cls == "UNRESOLVED": bp_unc += 1
        self.progress.set(
            "Calibrazioni salvate nel file corrente:\n"
            f"• Origine feeder: {root_n}\n"
            f"• Terminale MT XFR: {xfr_n}\n"
            f"• Breakpoint valutati: {bp_n} (continuità {bp_cont}, dispositivi {bp_dev}, non risolti {bp_unc})\n"
            f"• Bridge legacy: {bridge_i}\n"
            f"• Pattern gap: {bridge_p}"
        )

    def _close_guided(self):
        feeder_id = str((self._selected_feeder() or {}).get("feeder_id") or "")
        if feeder_id:
            a_ok = self._has_saved_action(MODE_ROOT, feeder_id)
            b_ok = self._has_saved_action(MODE_XFR, feeder_id)
            if not (a_ok and b_ok) and messagebox:
                missing = []
                if not a_ok: missing.append("PASSO A")
                if not b_ok: missing.append("PASSO B")
                if not messagebox.askyesno(
                    "Calibrazione incompleta",
                    f"Per {feeder_id} non risultano salvati: {', '.join(missing)}.\n\nVuoi chiudere comunque?",
                ):
                    return
        self.root.destroy()

    def _selected_feeder(self):
        sel = self.feeder_list.curselection()
        return self.feeders[int(sel[0])] if sel else (self.feeders[0] if self.feeders else {})

    def _selected_xfr_key(self):
        sel = self.xfr_list.curselection()
        if not sel:
            return None
        return str(self.xfr_list.get(int(sel[0])).split()[0]).replace("XFR_", "")

    def _load_feeder(self, idx):
        if not self.feeders:
            return
        idx = max(0, min(idx, len(self.feeders) - 1))
        self.feeder_list.selection_clear(0, tk.END)
        self.feeder_list.selection_set(idx)
        f = self.feeders[idx]
        members = [str(x) for x in f.get("member_cu_instance_keys", [])]
        self.xfr_list.delete(0, tk.END)
        for k in members:
            reps = self.xfr.get(k, [])
            page = reps[0]["page"] if reps else "?"
            self.xfr_list.insert(tk.END, f"XFR_{k}   pagina {page}")
        if members:
            self.xfr_list.selection_set(0)
        feeder_id = str(f.get("feeder_id") or "")
        if self.mode.get() not in {MODE_BRIDGE_INSTANCE, MODE_BRIDGE_PATTERN, MODE_BREAKPOINT_REVIEW}:
            # La procedura guidata riapre sempre sul primo passo non completato.
            if self._has_saved_action(MODE_ROOT, feeder_id):
                self.mode.set(MODE_XFR)
            else:
                self.mode.set(MODE_ROOT)
            self._refresh_save_button()
        if self.mode.get() == MODE_ROOT:
            self._focus_root()
        elif self.mode.get() in {MODE_BRIDGE_INSTANCE, MODE_BREAKPOINT_REVIEW}:
            self._focus_breakpoint()
        elif members:
            self._focus_xfr(members[0])
        self._reset_clicks()

    def _on_feeder(self, _e=None):
        sel = self.feeder_list.curselection()
        if sel:
            self._load_feeder(int(sel[0]))

    def _on_xfr(self, _e=None):
        k = self._selected_xfr_key()
        if k and self.mode.get() not in {MODE_ROOT, MODE_BRIDGE_INSTANCE, MODE_BREAKPOINT_REVIEW}:
            self._focus_xfr(k)
        self._reset_clicks()

    def _focus_xfr(self, k):
        reps = self.xfr.get(str(k), [])
        if not reps:
            self.selection_status.set(f"Nessun riferimento grafico trovato per XFR_{k}.")
            return
        r = reps[0]
        self._show_page(r["page"], fit=True)
        self.root.after(20, lambda: self._center_bbox(r["bbox"]))

    def _root_rep(self):
        f = self._selected_feeder()
        line = str(f.get("feeder_id") or "")
        reps = self.line_anchors.get(line, [])
        reps = sorted(reps, key=lambda r: (0 if r.get("style") == "DELIMITED" else 1, -r.get("bbox", [0,0,0,0])[1]))
        return reps[0] if reps else None

    def _focus_root(self):
        r = self._root_rep()
        if not r:
            self.selection_status.set("Non trovo un'etichetta feeder adatta su cui centrare la vista.")
            return
        self._show_page(r["page"], fit=True)
        self.root.after(20, lambda: self._center_bbox(r["bbox"]))

    def _breakpoint_rep(self):
        f = self._selected_feeder()
        feeder_id = str(f.get("feeder_id") or "")
        bps = []
        # Prefer the complete feeder trace in the analysis output; the request
        # context may intentionally contain only a short preview.
        fv = self.analysis.get("feeder_verification", {}) or {}
        trace = next((t for t in fv.get("feeder_traces", []) or [] if str(t.get("feeder_id") or "") == feeder_id), None)
        if trace:
            bps = list(trace.get("suggested_breakpoints", []) or [])
        if not bps:
            bps = list(f.get("suggested_breakpoints", []) or [])
        reviewed = set()
        for rec in self.feedback:
            val = rec.get("value", {}) or {}
            if val.get("action") != MODE_BREAKPOINT_REVIEW:
                continue
            reviewed.add((str(val.get("feeder_id") or ""), int(val.get("page") or 0), val.get("source_node_id"), val.get("target_node_id")))
        for bp in bps:
            key = (feeder_id, int(bp.get("page") or 0), bp.get("source_node_id"), bp.get("target_node_id"))
            if key not in reviewed:
                return bp
        return None

    def _focus_breakpoint(self):
        bp = self._breakpoint_rep()
        if not bp:
            self.selection_status.set("Nessun breakpoint suggerito per il feeder selezionato.")
            return
        self._show_page(bp.get("page", 1), fit=True)
        self.root.after(20, lambda: self._center_points(bp.get("point_a"), bp.get("point_b")))

    def _center_points(self, a, b):
        if not a or not b:
            return
        bbox = [min(a[0], b[0]) - 20, min(a[1], b[1]) - 20, max(a[0], b[0]) + 20, max(a[1], b[1]) + 20]
        self._center_bbox(bbox)

    def _show_page(self, page_no, fit=False):
        self.current_page = max(1, min(int(page_no), self.doc.page_count))
        page = self.doc[self.current_page - 1]
        self.root.update_idletasks()
        if fit:
            cw = max(self.canvas.winfo_width() - 30, 300)
            ch = max(self.canvas.winfo_height() - 30, 300)
            rr = page.rect
            self.fit_zoom = max(.12, min(cw / max(rr.width, 1), ch / max(rr.height, 1)))
            self.zoom = self.fit_zoom
        self._render()

    def _render(self):
        page = self.doc[self.current_page - 1]
        pix = page.get_pixmap(matrix=fitz.Matrix(self.zoom, self.zoom), alpha=False)
        enc = base64.b64encode(pix.tobytes("png")).decode("ascii")
        self.image = tk.PhotoImage(data=enc)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, image=self.image, anchor="nw")
        self.canvas.configure(scrollregion=(0, 0, pix.width, pix.height))

        if self.mode.get() == MODE_ROOT:
            r = self._root_rep(); reps = [r] if r else []
        elif self.mode.get() in {MODE_BRIDGE_INSTANCE, MODE_BREAKPOINT_REVIEW}:
            reps = []
        else:
            k = self._selected_xfr_key(); reps = self.xfr.get(str(k), []) if k else []
        for r in reps:
            if r["page"] != self.current_page:
                continue
            rr = pdf_rect_to_rotated_page(page, r["bbox"])
            self.canvas.create_rectangle(rr.x0*self.zoom, rr.y0*self.zoom, rr.x1*self.zoom, rr.y1*self.zoom, outline="#d97706", width=3)

        if self.mode.get() in {MODE_BRIDGE_INSTANCE, MODE_BREAKPOINT_REVIEW}:
            bp = self._breakpoint_rep()
            if bp and int(bp.get("page", 0)) == self.current_page:
                for label, pt in (("A", bp.get("point_a")), ("B", bp.get("point_b"))):
                    if pt:
                        self.canvas.create_oval(pt[0]*self.zoom-7, pt[1]*self.zoom-7, pt[0]*self.zoom+7, pt[1]*self.zoom+7, outline="#dc2626", width=3)
                        self.canvas.create_text(pt[0]*self.zoom+10, pt[1]*self.zoom, text=label, anchor="w")

        for i, p in enumerate(self.clicks):
            self.canvas.create_oval(p[0]*self.zoom-5, p[1]*self.zoom-5, p[0]*self.zoom+5, p[1]*self.zoom+5, outline="#2563eb", width=3)
            self.canvas.create_text(p[0]*self.zoom+10, p[1]*self.zoom, text=str(i+1), anchor="w")
        self.page_label.config(text=f"Pagina {self.current_page}/{self.doc.page_count} — zoom {self.zoom:.2f}x")

    def _center_bbox(self, bbox):
        page = self.doc[self.current_page - 1]
        rr = pdf_rect_to_rotated_page(page, bbox)
        cw = max(self.canvas.winfo_width() - 30, 300)
        ch = max(self.canvas.winfo_height() - 30, 300)
        desired = max(self.fit_zoom, min(min(cw / max(rr.width*8, 160), ch / max(rr.height*8, 160)), 5.0))
        if abs(desired - self.zoom) > .02:
            self.zoom = desired
            self._render()
            rr = pdf_rect_to_rotated_page(page, bbox)
        px = (rr.x0 + rr.x1) / 2 * self.zoom
        py = (rr.y0 + rr.y1) / 2 * self.zoom
        allb = self.canvas.bbox("all") or (0,0,1,1)
        tw = max(float(allb[2]), 1); th = max(float(allb[3]), 1)
        self.canvas.xview_moveto(max(0, min(1, (px - cw/2) / tw)))
        self.canvas.yview_moveto(max(0, min(1, (py - ch/2) / th)))

    def _mouse_zoom(self, event):
        self.zoom = max(.08, min(8.0, self.zoom * (1.2 if event.delta > 0 else 1/1.2)))
        self._render()

    def _click(self, event):
        if self.mode.get() == MODE_BREAKPOINT_REVIEW:
            self.selection_status.set("Per valutare il breakpoint non devi cliccare sullo schema: scegli una delle tre opzioni nella sezione 4 e registra la valutazione.")
            return
        x = self.canvas.canvasx(event.x) / self.zoom
        y = self.canvas.canvasy(event.y) / self.zoom
        page = self.doc[self.current_page - 1]
        pt = fitz.Point(x, y)
        pt = pt * page.derotation_matrix if page.rotation else pt
        pdfp = [round(pt.x, 3), round(pt.y, 3)]
        need = 1 if self.mode.get() in {MODE_XFR, MODE_ROOT} else 2
        if len(self.clicks) >= need:
            self.clicks = []
        self.clicks.append(pdfp)
        if len(self.clicks) == need and self.mode.get() == MODE_ROOT:
            msg = f"Punto selezionato. Ora premi «Conferma e salva PASSO A» (oppure Invio/Ctrl+S). Coordinate PDF: {pdfp}"
        elif len(self.clicks) == need and self.mode.get() == MODE_XFR:
            msg = f"Punto selezionato. Ora premi «Conferma e salva PASSO B» (oppure Invio/Ctrl+S). Coordinate PDF: {pdfp}"
        else:
            msg = f"Punti selezionati: {len(self.clicks)}/{need}. Coordinate PDF: {pdfp}"
        self.selection_status.set(msg)
        self._render()

    def _reset_clicks(self):
        self.clicks = []
        self.selection_status.set("Nessun punto selezionato.")
        self._update_instruction()
        if self.image is not None:
            self._render()

    def _save(self):
        f = self._selected_feeder()
        feeder_id = f.get("feeder_id")
        k = self._selected_xfr_key()
        mode = self.mode.get()
        need = 0 if mode == MODE_BREAKPOINT_REVIEW else (1 if mode in {MODE_XFR, MODE_ROOT} else 2)
        if len(self.clicks) != need:
            if messagebox:
                messagebox.showwarning("Selezione incompleta", f"Seleziona prima {need} punto/i sullo schema." if need else "Per questo passo non sono richiesti clic sullo schema.")
            return

        if mode == MODE_BREAKPOINT_REVIEW:
            bp = self._breakpoint_rep()
            if not bp:
                if messagebox:
                    messagebox.showinfo("Nessun breakpoint", "Non ci sono altri breakpoint suggeriti da valutare per il feeder selezionato.")
                return
            cls = str(self.breakpoint_decision.get() or "").upper()
            if cls not in {"CONDUCTIVE_CONTINUITY", "INTERPOSED_DEVICE", "NON_ELECTRICAL_GRAPHIC", "UNRESOLVED"}:
                if messagebox:
                    messagebox.showwarning("Valutazione mancante", "Scegli prima una delle tre opzioni nella sezione 4.")
                return
            display_to_type = {
                "Non determinato": "UNDETERMINED",
                "Cabina di sezionamento / Sectionalizing cabinet": "SECTIONALIZING_CABINET",
                "Sezionatore / Interruttore di manovra": "SWITCH_DISCONNECTOR",
                "Interruttore automatico / Circuit breaker": "CIRCUIT_BREAKER",
                "Trasformatore": "TRANSFORMER",
                "Altro dispositivo elettrico": "OTHER_ELECTRICAL_DEVICE",
            }
            value = derive_breakpoint_review_value(
                bp, classification=cls,
                device_type=display_to_type.get(self.breakpoint_device_display.get(), "UNDETERMINED"),
            )
        elif mode == MODE_XFR:
            reps = [r for r in self.xfr.get(str(k), []) if r["page"] == self.current_page]
            if not reps:
                reps = self.xfr.get(str(k), [])
            if not reps:
                return
            value = derive_xfr_binding_value(reps[0]["bbox"], self.clicks[0], feeder_id=feeder_id, xfr_instance_key=k, page=self.current_page)
        elif mode == MODE_ROOT:
            r = self._root_rep()
            if not r:
                if messagebox:
                    messagebox.showerror(
                        "Origine feeder non salvata",
                        "Non è stato trovato un riferimento grafico valido per il feeder selezionato. Il PASSO A NON è stato registrato. Cambia feeder o chiudi la GUI e segnala questo caso.",
                    )
                self.selection_status.set("ERRORE: PASSO A non salvato — riferimento feeder non trovato.")
                return
            value = derive_feeder_root_value(r["bbox"], self.clicks[0], feeder_id=feeder_id, anchor_text=r.get("text"), page=self.current_page)
        elif mode == MODE_BRIDGE_INSTANCE:
            value = derive_instance_bridge_value(self.clicks[0], self.clicks[1], feeder_id=feeder_id, page=self.current_page)
        else:
            value = derive_bridge_value(self.clicks[0], self.clicks[1], feeder_id=feeder_id, page=self.current_page, xfr_instance_key=k)

        rec = {
            "request_id": f"{self.req.get('request_id')}::{mode}::{len(self.feedback)+1}",
            "target": "FEEDER_ELECTRICAL_PATH_VERIFICATION",
            "option": "PROVIDE_VALUE",
            "status": "OPERATOR_PROVIDED",
            "plant_id": self.plant_id,
            "doc": self.pdf_path.name,
            "page": self.current_page,
            "learning_scope": "INSTANCE" if mode == MODE_BREAKPOINT_REVIEW else "PLANT",
            "value": value,
            "context": {
                "plant_id": self.plant_id,
                "interaction_mode": "VISUAL_SELECT_OR_CONFIRM_BREAKPOINT",
                "analysis_file": self.analysis_path.name,
                "selection_source": "OPERATOR_FEEDER_GUI_GUIDED_IT",
            },
        }
        rec = validate_feedback(rec)
        self._upsert_feedback(rec)
        _write_feedback(self.feedback_path, self.feedback)
        self._refresh_progress()

        if mode == MODE_ROOT:
            # Dopo il passo A portiamo automaticamente al passo B.
            if messagebox:
                messagebox.showinfo("PASSO A SALVATO ✓", f"Origine elettrica di {feeder_id} registrata correttamente.\n\nOra il programma passa al PASSO B.")
            self._set_mode(MODE_XFR)
        elif mode == MODE_XFR:
            if messagebox:
                messagebox.showinfo(
                    "PASSO B SALVATO ✓ — calibrazione minima completata",
                    f"Terminale MT di XFR_{k} registrato correttamente.\n\nPASSO A e PASSO B risultano ora salvati per {feeder_id}. Puoi chiudere la finestra e rilanciare il motore, oppure esaminare un breakpoint se richiesto.",
                )
            self._reset_clicks()
        elif mode == MODE_BREAKPOINT_REVIEW:
            cls = str(value.get("classification") or "")
            if cls == "CONDUCTIVE_CONTINUITY":
                msg = "Breakpoint registrato come continuità grafica. Il motore potrà creare un bridge ESATTO solo per questa istanza."
            elif cls == "INTERPOSED_DEVICE":
                msg = f"Breakpoint registrato come dispositivo interposto ({value.get('device_type')}). Nessun bridge è stato creato."
            else:
                msg = "Breakpoint lasciato non risolto. Nessun bridge è stato creato."
            if messagebox:
                messagebox.showinfo("Valutazione breakpoint salvata", msg + "\n\nPuoi esaminare il successivo oppure chiudere e rilanciare il motore.")
            self.breakpoint_decision.set("")
            self.breakpoint_device_display.set("Non determinato")
            self._reset_clicks()
            self._focus_breakpoint()
        else:
            if messagebox:
                messagebox.showinfo("Calibrazione salvata", f"La calibrazione avanzata è stata salvata in:\n{self.feedback_path}")
            self._reset_clicks()

    def run(self):
        self.root.mainloop()


def main():
    ap = argparse.ArgumentParser(
        prog="sld-ci-operator-feeder",
        description="Calibrazione grafica guidata, plant-scoped, per la verifica del percorso elettrico dei feeder",
    )
    ap.add_argument("--sld", required=True)
    ap.add_argument("--analysis", required=True)
    ap.add_argument("--feedback", required=True)
    args = ap.parse_args()
    FeederCalibrationApp(args.sld, args.analysis, args.feedback).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
