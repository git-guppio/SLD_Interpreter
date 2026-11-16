"""Tkinter visual resolver for open human-in-the-loop requests.

The tool is intentionally downstream of automatic inference. It never changes
source detection. It writes OPERATOR_PROVIDED feedback records that can be fed
back to ``cli.py --operator-feedback``.

Workflow::

    python -m sld_ci_v04_beta2_dev11.operator_visual \
        --pdf PV10.pdf \
        --analysis output/PV10_dev5.json \
        --feedback output/PV10_operator_feedback.json

For VISUAL_SELECT requests the operator can navigate the relevant pages,
inspect highlighted unresolved candidates, draw a rectangle around a device,
choose its target class and save the selection. The other two valid outcomes
("not represented" and "unable to identify") are also preserved explicitly.
"""
from __future__ import annotations

import argparse
import base64
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pymupdf as fitz

from .operator_interaction import validate_feedback

try:  # imported lazily enough that --help remains usable on headless systems
    import tkinter as tk
    from tkinter import messagebox, ttk
except Exception:  # pragma: no cover - platform dependent
    tk = None
    ttk = None
    messagebox = None


@dataclass
class VisualHint:
    group_id: str
    page: int
    bbox: List[float]
    candidate_type: Optional[str] = None
    morph_family_id: Optional[str] = None
    family_size: Optional[int] = None
    terminal_count: Optional[int] = None
    rating_text: Optional[str] = None


def _load_json(path: str | Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _open_visual_requests(analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
    reqs = analysis.get("interpretation", {}).get("resolution_requests", [])
    return [
        r for r in reqs
        if r.get("status", "OPEN") == "OPEN" and r.get("interaction_mode") == "VISUAL_SELECT"
    ]


def _profile_index(analysis: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {
        p.get("group_id"): p
        for p in analysis.get("interpretation", {}).get("candidate_feature_profiles", [])
        if p.get("group_id")
    }


def _visual_hints(request: Dict[str, Any], analysis: Dict[str, Any]) -> List[VisualHint]:
    raw = list((request.get("context") or {}).get("visual_hints") or [])
    if not raw:
        idx = _profile_index(analysis)
        for gid in request.get("group_ids", []):
            p = idx.get(gid) or {}
            bbox = (p.get("geometry") or {}).get("bbox")
            page = p.get("page")
            if bbox and page:
                raw.append({
                    "group_id": gid,
                    "page": page,
                    "bbox": bbox,
                    "candidate_type": p.get("candidate_type"),
                    "morph_family_id": (p.get("repetition") or {}).get("morph_family_id"),
                    "family_size": (p.get("repetition") or {}).get("family_size"),
                    "terminal_count": (p.get("topology") or {}).get("terminal_count"),
                })
    out: List[VisualHint] = []
    for x in raw:
        if not x.get("group_id") or x.get("page") is None or not x.get("bbox"):
            continue
        out.append(VisualHint(
            group_id=str(x["group_id"]),
            page=int(x["page"]),
            bbox=[float(v) for v in x["bbox"]],
            candidate_type=x.get("candidate_type"),
            morph_family_id=x.get("morph_family_id"),
            family_size=x.get("family_size"),
            terminal_count=x.get("terminal_count"),
            rating_text=x.get("rating_text"),
        ))
    return out


def pdf_rect_to_rotated_page(page: fitz.Page, bbox: List[float]) -> fitz.Rect:
    """Map stored PDF coordinates to the coordinates used by the rendered page."""
    rect = fitz.Rect(*bbox)
    if page.rotation:
        rect = rect * page.rotation_matrix
    return rect


def rotated_page_rect_to_pdf(page: fitz.Page, rect: fitz.Rect) -> fitz.Rect:
    """Inverse of :func:`pdf_rect_to_rotated_page` for operator selections."""
    if page.rotation:
        rect = rect * page.derotation_matrix
    return rect


def _read_existing_feedback(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    obj = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        return list(obj.get("operator_feedback", obj.get("records", [])) or [])
    return []


def _write_feedback(path: Path, records: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"operator_feedback": records}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


class VisualResolverApp:
    def __init__(
        self,
        pdf_path: str,
        analysis_path: str,
        feedback_path: str,
        request_id: Optional[str] = None,
    ) -> None:
        if tk is None or ttk is None:
            raise RuntimeError("Tkinter is not available in this Python installation")

        self.pdf_path = Path(pdf_path)
        self.analysis_path = Path(analysis_path)
        self.feedback_path = Path(feedback_path)
        self.analysis = _load_json(self.analysis_path)
        self.doc = fitz.open(self.pdf_path)
        self.requests = _open_visual_requests(self.analysis)
        if request_id:
            self.requests = [r for r in self.requests if r.get("request_id") == request_id]
        if not self.requests:
            raise ValueError("No open VISUAL_SELECT resolution requests found in the analysis JSON")

        self.feedback_records = _read_existing_feedback(self.feedback_path)
        answered = {x.get("request_id") for x in self.feedback_records if x.get("request_id")}
        remaining = [r for r in self.requests if r.get("request_id") not in answered]
        self.requests = remaining or self.requests

        self.req_index = 0
        self.hints: List[VisualHint] = []
        self.hint_index = 0
        self.current_page_no = 1
        self.zoom = 1.0
        self.fit_zoom = 1.0
        self.image = None
        self.selection_start: Optional[Tuple[float, float]] = None
        self.selection_rect_canvas: Optional[int] = None
        self.selection_bbox_pdf: Optional[List[float]] = None
        self.candidate_rect_ids: List[int] = []

        self.root = tk.Tk()
        self.root.title("Electrical SLD Interpreter — Operator Visual Resolver")
        self.root.geometry("1450x900")
        self._build_ui()
        self._load_request(0)

    def _build_ui(self) -> None:
        top = ttk.Frame(self.root, padding=6)
        top.pack(side=tk.TOP, fill=tk.X)

        self.request_label = ttk.Label(top, text="", anchor="w")
        self.request_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        ttk.Button(top, text="Previous request", command=self._previous_request).pack(side=tk.RIGHT, padx=2)
        ttk.Button(top, text="Next request", command=self._next_request).pack(side=tk.RIGHT, padx=2)

        body = ttk.Panedwindow(self.root, orient=tk.HORIZONTAL)
        body.pack(fill=tk.BOTH, expand=True)

        left = ttk.Frame(body, padding=6, width=310)
        center = ttk.Frame(body)
        body.add(left, weight=0)
        body.add(center, weight=1)

        ttk.Label(left, text="Unresolved candidates").pack(anchor="w")
        self.hint_list = tk.Listbox(left, exportselection=False, width=46, height=22)
        self.hint_list.pack(fill=tk.BOTH, expand=False, pady=(2, 8))
        self.hint_list.bind("<<ListboxSelect>>", self._on_hint_select)

        ttk.Label(left, text="Device class").pack(anchor="w")
        self.device_type = tk.StringVar()
        self.device_combo = ttk.Combobox(left, textvariable=self.device_type, state="readonly")
        self.device_combo.pack(fill=tk.X, pady=(2, 8))

        self.status_text = tk.StringVar(value="Draw a rectangle around the target device.")
        ttk.Label(left, textvariable=self.status_text, wraplength=290).pack(anchor="w", pady=(0, 8))

        ttk.Button(left, text="Save selected device", command=self._save_selection).pack(fill=tk.X, pady=2)
        ttk.Button(left, text="Not represented in SLD", command=self._not_represented).pack(fill=tk.X, pady=2)
        ttk.Button(left, text="Unable to identify", command=self._unable_to_identify).pack(fill=tk.X, pady=2)
        ttk.Separator(left, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)
        ttk.Button(left, text="Focus candidate", command=self._focus_current_hint).pack(fill=tk.X, pady=2)
        ttk.Button(left, text="Show whole page", command=self._fit_page).pack(fill=tk.X, pady=2)

        zoom_row = ttk.Frame(left)
        zoom_row.pack(fill=tk.X, pady=4)
        ttk.Button(zoom_row, text="Zoom -", command=lambda: self._set_zoom(self.zoom / 1.25)).pack(side=tk.LEFT, expand=True, fill=tk.X)
        ttk.Button(zoom_row, text="Zoom +", command=lambda: self._set_zoom(self.zoom * 1.25)).pack(side=tk.LEFT, expand=True, fill=tk.X)

        self.page_label = ttk.Label(left, text="")
        self.page_label.pack(anchor="w", pady=(6, 0))

        self.canvas = tk.Canvas(center, background="white", cursor="cross")
        xbar = ttk.Scrollbar(center, orient=tk.HORIZONTAL, command=self.canvas.xview)
        ybar = ttk.Scrollbar(center, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=xbar.set, yscrollcommand=ybar.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        ybar.grid(row=0, column=1, sticky="ns")
        xbar.grid(row=1, column=0, sticky="ew")
        center.rowconfigure(0, weight=1)
        center.columnconfigure(0, weight=1)

        self.canvas.bind("<ButtonPress-1>", self._selection_press)
        self.canvas.bind("<B1-Motion>", self._selection_drag)
        self.canvas.bind("<ButtonRelease-1>", self._selection_release)
        self.canvas.bind("<Control-MouseWheel>", self._mouse_zoom)

    @property
    def current_request(self) -> Dict[str, Any]:
        return self.requests[self.req_index]

    def _load_request(self, idx: int) -> None:
        self.req_index = max(0, min(idx, len(self.requests) - 1))
        req = self.current_request
        self.hints = _visual_hints(req, self.analysis)
        self.hint_index = 0
        allowed = list((req.get("context") or {}).get("allowed_target_classes") or [])
        if not allowed:
            allowed = ["MV_LV_TRANSFORMER", "LV_LV_TRANSFORMER", "OTHER_ELECTRICAL"]
        self.device_combo["values"] = allowed
        self.device_type.set(allowed[0])

        self.request_label.configure(
            text=f"Request {self.req_index + 1}/{len(self.requests)} — {req.get('request_id')} — {req.get('reason')}"
        )
        self.hint_list.delete(0, tk.END)
        for i, h in enumerate(self.hints):
            extra = []
            if h.morph_family_id:
                extra.append(str(h.morph_family_id))
            if h.family_size is not None:
                extra.append(f"family={h.family_size}")
            if h.terminal_count is not None:
                extra.append(f"term={h.terminal_count}")
            if h.rating_text:
                extra.append(f"rating={h.rating_text}")
            suffix = " | ".join(extra)
            self.hint_list.insert(tk.END, f"p{h.page}  {h.group_id}" + (f"  [{suffix}]" if suffix else ""))
        if self.hints:
            self.hint_list.selection_set(0)
            self._show_hint(0)
        else:
            pages = list((req.get("context") or {}).get("pages_involved") or [])
            self._show_page(int(pages[0]) if pages else int(req.get("page") or 1), fit=True)

    def _previous_request(self) -> None:
        if self.req_index > 0:
            self._load_request(self.req_index - 1)

    def _next_request(self) -> None:
        if self.req_index + 1 < len(self.requests):
            self._load_request(self.req_index + 1)

    def _on_hint_select(self, _event=None) -> None:
        sel = self.hint_list.curselection()
        if sel:
            self._show_hint(int(sel[0]))

    def _show_hint(self, idx: int) -> None:
        if not self.hints:
            return
        self.hint_index = max(0, min(idx, len(self.hints) - 1))
        h = self.hints[self.hint_index]
        self._show_page(h.page, fit=True)
        self.root.after(30, self._focus_current_hint)

    def _fit_page(self) -> None:
        self._show_page(self.current_page_no, fit=True)

    def _show_page(self, page_no: int, fit: bool = False) -> None:
        page_no = max(1, min(page_no, self.doc.page_count))
        self.current_page_no = page_no
        page = self.doc[page_no - 1]
        self.root.update_idletasks()
        if fit:
            cw = max(self.canvas.winfo_width() - 30, 300)
            ch = max(self.canvas.winfo_height() - 30, 300)
            r = page.rect
            self.fit_zoom = max(0.12, min(cw / max(r.width, 1.0), ch / max(r.height, 1.0)))
            self.zoom = self.fit_zoom
        self._render_page()

    def _set_zoom(self, value: float) -> None:
        self.zoom = max(0.08, min(float(value), 8.0))
        self._render_page()

    def _mouse_zoom(self, event) -> None:
        factor = 1.2 if event.delta > 0 else 1 / 1.2
        self._set_zoom(self.zoom * factor)

    def _render_page(self) -> None:
        page = self.doc[self.current_page_no - 1]
        pix = page.get_pixmap(matrix=fitz.Matrix(self.zoom, self.zoom), alpha=False)
        encoded = base64.b64encode(pix.tobytes("png")).decode("ascii")
        self.image = tk.PhotoImage(data=encoded)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, image=self.image, anchor="nw", tags=("page",))
        self.canvas.configure(scrollregion=(0, 0, pix.width, pix.height))
        self.selection_rect_canvas = None
        self.selection_bbox_pdf = None
        self.candidate_rect_ids = []

        # Highlight unresolved groups only as navigation aids; they are not labels.
        for h in self.hints:
            if h.page != self.current_page_no:
                continue
            rr = pdf_rect_to_rotated_page(page, h.bbox)
            cid = self.canvas.create_rectangle(
                rr.x0 * self.zoom, rr.y0 * self.zoom,
                rr.x1 * self.zoom, rr.y1 * self.zoom,
                outline="#d97706", width=2,
                tags=("candidate", h.group_id),
            )
            self.candidate_rect_ids.append(cid)
        self.page_label.configure(text=f"Page {self.current_page_no}/{self.doc.page_count} — zoom {self.zoom:.2f}x")

    def _focus_current_hint(self) -> None:
        if not self.hints:
            return
        h = self.hints[self.hint_index]
        if h.page != self.current_page_no:
            self._show_page(h.page, fit=True)
        page = self.doc[self.current_page_no - 1]
        rr = pdf_rect_to_rotated_page(page, h.bbox)
        # Aim for the candidate to occupy roughly 20% of the viewport, with context.
        target_w = max(rr.width * 6.0, 120.0)
        target_h = max(rr.height * 6.0, 120.0)
        cw = max(self.canvas.winfo_width() - 30, 300)
        ch = max(self.canvas.winfo_height() - 30, 300)
        desired = min(cw / target_w, ch / target_h)
        desired = max(self.fit_zoom, min(desired, 5.0))
        if abs(desired - self.zoom) > 0.02:
            self.zoom = desired
            self._render_page()
            rr = pdf_rect_to_rotated_page(page, h.bbox)
        px = ((rr.x0 + rr.x1) / 2.0) * self.zoom
        py = ((rr.y0 + rr.y1) / 2.0) * self.zoom
        bbox = self.canvas.bbox("all") or (0, 0, 1, 1)
        total_w = max(float(bbox[2]), 1.0)
        total_h = max(float(bbox[3]), 1.0)
        self.canvas.xview_moveto(max(0.0, min(1.0, (px - cw / 2) / total_w)))
        self.canvas.yview_moveto(max(0.0, min(1.0, (py - ch / 2) / total_h)))

    def _canvas_xy(self, event) -> Tuple[float, float]:
        return self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)

    def _selection_press(self, event) -> None:
        self.selection_start = self._canvas_xy(event)
        if self.selection_rect_canvas is not None:
            self.canvas.delete(self.selection_rect_canvas)
        x, y = self.selection_start
        self.selection_rect_canvas = self.canvas.create_rectangle(x, y, x, y, outline="#2563eb", width=3)
        self.selection_bbox_pdf = None

    def _selection_drag(self, event) -> None:
        if self.selection_start is None or self.selection_rect_canvas is None:
            return
        x0, y0 = self.selection_start
        x1, y1 = self._canvas_xy(event)
        self.canvas.coords(self.selection_rect_canvas, x0, y0, x1, y1)

    def _selection_release(self, event) -> None:
        if self.selection_start is None:
            return
        x0, y0 = self.selection_start
        x1, y1 = self._canvas_xy(event)
        self.selection_start = None
        xa, xb = sorted((x0, x1)); ya, yb = sorted((y0, y1))
        if xb - xa < 4 or yb - ya < 4:
            self.selection_bbox_pdf = None
            self.status_text.set("Selection too small. Draw a rectangle around the device.")
            return
        page = self.doc[self.current_page_no - 1]
        rotated = fitz.Rect(xa / self.zoom, ya / self.zoom, xb / self.zoom, yb / self.zoom)
        pdf_rect = rotated_page_rect_to_pdf(page, rotated)
        pdf_rect = pdf_rect & page.rect
        self.selection_bbox_pdf = [round(pdf_rect.x0, 3), round(pdf_rect.y0, 3), round(pdf_rect.x1, 3), round(pdf_rect.y1, 3)]
        self.status_text.set(f"Selected bbox PDF: {self.selection_bbox_pdf}")

    def _base_feedback(self, option: str) -> Dict[str, Any]:
        req = self.current_request
        return {
            "request_id": req.get("request_id"),
            "target": req.get("target"),
            "option": option,
            "status": "OPERATOR_PROVIDED",
            "doc": req.get("doc"),
            "page": self.current_page_no,
            "context": {
                "interaction_mode": "VISUAL_SELECT",
                "analysis_file": self.analysis_path.name,
                "selection_source": "OPERATOR_VISUAL_GUI",
            },
        }

    def _append_feedback(self, record: Dict[str, Any]) -> None:
        record = validate_feedback(record)
        # One terminal outcome per request in the feedback file. This avoids an old
        # answer silently surviving after an operator deliberately changes it.
        self.feedback_records = [x for x in self.feedback_records if x.get("request_id") != record.get("request_id")]
        self.feedback_records.append(record)
        _write_feedback(self.feedback_path, self.feedback_records)
        self.status_text.set(f"Saved: {record['option']} → {self.feedback_path}")
        if messagebox:
            messagebox.showinfo("Saved", f"Operator feedback saved to:\n{self.feedback_path}")

    def _save_selection(self) -> None:
        if not self.selection_bbox_pdf:
            if messagebox:
                messagebox.showwarning("Missing selection", "Draw a rectangle around the device first.")
            return
        rec = self._base_feedback("SELECT_DEVICE")
        rec["bbox"] = self.selection_bbox_pdf
        rec["device_type"] = self.device_type.get()
        if self.hints:
            rec["context"]["focused_group_id"] = self.hints[self.hint_index].group_id
        self._append_feedback(rec)

    def _not_represented(self) -> None:
        self._append_feedback(self._base_feedback("NOT_REPRESENTED_IN_SLD"))

    def _unable_to_identify(self) -> None:
        self._append_feedback(self._base_feedback("UNABLE_TO_IDENTIFY"))

    def run(self) -> None:
        self.root.mainloop()


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="sld-ci-operator-visual",
        description="Visual human-in-the-loop resolver for SLD Interpreter requests",
    )
    parser.add_argument("--pdf", required=True, help="Original SLD PDF used to create the analysis JSON")
    parser.add_argument("--analysis", required=True, help="Interpreter JSON containing resolution_requests")
    parser.add_argument("--feedback", required=True, help="Output/updated operator feedback JSON")
    parser.add_argument("--request-id", default=None, help="Optional single request ID to open")
    args = parser.parse_args()

    app = VisualResolverApp(args.pdf, args.analysis, args.feedback, request_id=args.request_id)
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
