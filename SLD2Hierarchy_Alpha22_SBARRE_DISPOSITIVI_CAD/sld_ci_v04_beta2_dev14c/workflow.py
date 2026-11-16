"""Avvio semplificato del progetto SLD Interpreter — dev14c.

Un solo comando per CASE:
    python -m sld_ci_v04_beta2_dev14c.workflow --case ..\data\CASE_004_PV4

Il modulo scopre i PDF, esegue l'analisi senza riversare centinaia di righe in
console, mostra un riepilogo leggibile e, solo se serve, apre automaticamente
la GUI con UNA richiesta operatore alla volta.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import shutil
import re
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import pymupdf as fitz

from .cli import run_case
from .config import RunConfig
from .operator_simple import SimpleOperatorApp, choose_next_task
from .operator_feeder import _read_feedback
from .operator_interaction import validate_feedback_batch


def discover_case(case_dir: Path) -> Tuple[Path, Optional[Path], Path, str]:
    case_dir = case_dir.resolve()
    input_dir = case_dir / "input"
    output_dir = case_dir / "output"
    if not input_dir.exists():
        raise FileNotFoundError(f"Cartella input non trovata: {input_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    pdfs = sorted(input_dir.glob("*.pdf"))
    if not pdfs:
        raise FileNotFoundError(f"Nessun PDF in {input_dir}")
    sld = next((p for p in pdfs if p.stem.upper().endswith("_SLD")), None)
    layout = next((p for p in pdfs if p.stem.upper().endswith("_LAYOUT")), None)
    if sld is None:
        others = [p for p in pdfs if p != layout]
        if len(others) == 1:
            sld = others[0]
        else:
            raise ValueError("Non riesco a individuare univocamente il PDF SLD. Usa un nome *_SLD.pdf.")
    stem = sld.stem[:-4] if sld.stem.upper().endswith("_SLD") else sld.stem
    return sld, layout, output_dir, stem


def _valid_feedback_file(path: Path) -> bool:
    try:
        rows = _read_feedback(path)
        validate_feedback_batch(rows)
        return bool(rows)
    except Exception:
        return False


def ensure_canonical_feedback(output_dir: Path, stem: str) -> Path:
    canonical = output_dir / f"{stem}_operator_feedback.json"
    if canonical.exists():
        return canonical
    candidates = [p for p in output_dir.glob("*.json") if "feedback" in p.name.lower() and p != canonical and _valid_feedback_file(p)]
    if candidates:
        candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        shutil.copy2(candidates[0], canonical)
        print(f"Feedback precedente recuperato automaticamente: {candidates[0].name}")
    return canonical


def _compact_summary(result: Dict[str, Any]) -> Dict[str, Any]:
    tc = result.get("target_counts", {}) or {}
    fv = (result.get("feeder_verification", {}) or {}).get("summary", {}) or {}
    sr = (result.get("source_reconciliation", {}) or {}).get("summary", {}) or {}
    return {
        "cu": int(tc.get("conversion_units") or 0),
        "tr": int(tc.get("mv_lv_transformers") or 0),
        "inv": int(tc.get("inverters") or 0),
        "sb": int(tc.get("string_boxes") or 0),
        "feeders": int(sr.get("mv_line_count") or fv.get("explicit_schedule_feeder_count") or 0),
        "membership": int(sr.get("resolved_cu_mv_membership_count") or fv.get("explicit_schedule_membership_count") or 0),
        "graph_verified": int(fv.get("graph_verified_cu_mv_membership_count") or 0),
        "fully_verified": int(fv.get("fully_graph_verified_feeder_count") or 0),
        "end_to_end": int(fv.get("end_to_end_graph_trace_complete_count") or 0),
        "breakpoints": int(fv.get("suggested_breakpoint_count") or 0),
        "hard_conflicts": int(sr.get("membership_hard_conflict_count") or fv.get("graph_conflict_count") or 0),
    }


def print_summary(result: Dict[str, Any], analysis_path: Path, log_path: Path) -> None:
    s = _compact_summary(result)
    plant = (result.get("plant", {}) or {}).get("plant_id") or "impianto"
    print("\n" + "="*62)
    print(f"RISULTATO SINTETICO — {plant}")
    print("="*62)
    print(f"Gerarchia: {s['cu']} CU | {s['tr']} TR MV/LV | {s['inv']} inverter | {s['sb']} string/combiner box")
    if s["feeders"]:
        print(f"Feeder: {s['feeders']} | CU assegnate: {s['membership']}/{s['cu']} | verificate sul grafo: {s['graph_verified']}/{s['cu']}")
        print(f"Feeder completamente verificati: {s['fully_verified']}/{s['feeders']} | end-to-end: {s['end_to_end']}/{s['feeders']}")
    if s["hard_conflicts"]:
        print(f"ATTENZIONE: {s['hard_conflicts']} conflitti da verificare.")
    task = choose_next_task(result, _read_feedback(Path(result.get('_workflow_feedback_path',''))) if result.get('_workflow_feedback_path') else [])
    if task:
        kind = task.get("kind")
        if kind == "BIND_FEEDER_ROOT_PATTERN":
            next_text = "indicare una volta l'origine elettrica di un feeder rappresentativo"
        elif kind == "BIND_XFR_MV_TERMINAL_PATTERN":
            next_text = "indicare una volta il terminale MT di un trasformatore rappresentativo"
        else:
            next_text = f"verificare visivamente un punto di interruzione sul feeder {task.get('feeder',{}).get('feeder_id')}"
        print(f"Prossimo contributo operatore: {next_text}.")
    else:
        print("Nessuna richiesta operatore immediata.")
    print(f"Dettagli completi: {analysis_path}")
    print(f"Log tecnico:       {log_path}")
    print("="*62 + "\n")


class _ProgressReporter:
    """Indicatore console leggero: percentuale stimata + heartbeat temporale."""

    def __init__(self, sld_pages: int, layout_pages: int, stream=None):
        self.sld_pages = max(0, int(sld_pages))
        self.layout_pages = max(0, int(layout_pages))
        self.total_pages = max(1, self.sld_pages + self.layout_pages)
        self.stream = stream or sys.__stdout__
        self.started = time.monotonic()
        self.percent = 2
        self.phase = "avvio analisi"
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._heartbeat, daemon=True)
        self._last_render_len = 0

    def start(self) -> None:
        self._render()
        self._thread.start()

    def update_page(self, source_kind: str, page_no: int, page_total: int) -> None:
        if source_kind == "SLD":
            processed = min(page_no, self.sld_pages)
            phase = f"SLD pagina {page_no}/{page_total}"
        else:
            processed = self.sld_pages + min(page_no, self.layout_pages)
            phase = f"LAYOUT pagina {page_no}/{page_total}"
        # Le pagine coprono l'80%: il restante 20% e' dedicato a
        # riconciliazione, gerarchia, feeder e scrittura output.
        pct = min(82, 2 + round(80 * processed / self.total_pages))
        with self._lock:
            self.percent = pct
            self.phase = phase
        self._render()

    def postprocess(self) -> None:
        with self._lock:
            self.percent = max(self.percent, 85)
            self.phase = "ricostruzione gerarchia e topologia"
        self._render()

    def complete(self) -> None:
        with self._lock:
            self.percent = 100
            self.phase = "completata"
        self._render(final=True)
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=0.2)

    def fail(self) -> None:
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=0.2)
        try:
            self.stream.write("\n")
            self.stream.flush()
        except Exception:
            pass

    def _heartbeat(self) -> None:
        while not self._stop.wait(2.0):
            self._render()

    def _render(self, final: bool = False) -> None:
        with self._lock:
            pct = self.percent
            phase = self.phase
        elapsed = int(time.monotonic() - self.started)
        mins, secs = divmod(elapsed, 60)
        bar_len = 20
        filled = max(0, min(bar_len, round(bar_len * pct / 100)))
        bar = "#" * filled + "-" * (bar_len - filled)
        line = f"Analisi [{bar}] {pct:3d}% | {phase} | {mins:02d}:{secs:02d}"
        try:
            # Pad with spaces when the new status is shorter than the previous
            # one. This avoids stale tail fragments in Windows PowerShell
            # (e.g. "...02:41rchia e topologia").
            pad = " " * max(0, self._last_render_len - len(line))
            self.stream.write("\r" + line + pad + ("\n" if final else ""))
            self.stream.flush()
            self._last_render_len = len(line)
        except Exception:
            pass


class _ProgressCapture(io.TextIOBase):
    _page_re = re.compile(r"\[[^\]]+\|\s*(SLD|LAYOUT)\]\s*page\s+(\d+)/(\d+)")

    def __init__(self, log_buffer: io.StringIO, reporter: _ProgressReporter):
        self.log_buffer = log_buffer
        self.reporter = reporter
        self._pending = ""
        self._last_page_seen = 0

    def write(self, text: str) -> int:
        self.log_buffer.write(text)
        self._pending += text
        while "\n" in self._pending:
            line, self._pending = self._pending.split("\n", 1)
            m = self._page_re.search(line)
            if m:
                kind, pno, ptotal = m.group(1), int(m.group(2)), int(m.group(3))
                self.reporter.update_page(kind, pno, ptotal)
                if ((kind == "LAYOUT" and pno == ptotal) or
                    (kind == "SLD" and pno == ptotal and self.reporter.layout_pages == 0)):
                    self.reporter.postprocess()
        return len(text)

    def flush(self) -> None:
        return None


def _pdf_page_count(path: Optional[Path]) -> int:
    if path is None:
        return 0
    try:
        with fitz.open(str(path)) as doc:
            return int(doc.page_count)
    except Exception:
        return 0


def run_quiet(sld: Path, layout: Optional[Path], analysis_path: Path, knowledge: Path, feedback: Path, log_path: Path) -> Dict[str, Any]:
    buf = io.StringIO()
    reporter = _ProgressReporter(_pdf_page_count(sld), _pdf_page_count(layout))
    sink = _ProgressCapture(buf, reporter)
    cfg = RunConfig(dpi=150, lang="eng+spa", ocr_mode="auto", max_pages=None)
    reporter.start()
    try:
        with contextlib.redirect_stdout(sink):
            result = run_case(
                str(sld), str(analysis_path), cfg,
                layout_path=str(layout) if layout else None,
                knowledge_path=str(knowledge),
                operator_feedback_path=str(feedback) if feedback.exists() else None,
            )
        reporter.complete()
    except Exception:
        reporter.fail()
        raise
    finally:
        log_path.write_text(buf.getvalue(), encoding="utf-8")
    result["_workflow_feedback_path"] = str(feedback)
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="SLD Interpreter — flusso operatore semplificato")
    ap.add_argument("--case", required=True, help="Cartella CASE, ad es. ..\\data\\CASE_004_PV4")
    ap.add_argument("--no-gui", action="store_true", help="Esegue solo l'analisi sintetica senza aprire la GUI")
    args = ap.parse_args()

    case_dir = Path(args.case)
    sld, layout, output_dir, stem = discover_case(case_dir)
    pkg_dir = Path(__file__).resolve().parent
    knowledge = pkg_dir / "knowledge" / "knowledge_store.json"
    feedback = ensure_canonical_feedback(output_dir, stem)
    analysis_path = output_dir / f"{stem}_dev14c.json"
    log_path = output_dir / f"{stem}_dev14c_full.log"

    print(f"Analisi di {stem} in corso... (il dettaglio tecnico viene salvato nel log)")
    result = run_quiet(sld, layout, analysis_path, knowledge, feedback, log_path)
    print_summary(result, analysis_path, log_path)

    if args.no_gui:
        return 0
    rows = _read_feedback(feedback)
    task = choose_next_task(result, rows)
    if not task:
        return 0

    print("Apro automaticamente la finestra con la sola verifica richiesta...")
    before = len(rows)
    app = SimpleOperatorApp(str(sld), str(analysis_path), str(feedback))
    saved = app.run()
    after = len(_read_feedback(feedback)) if feedback.exists() else 0
    if not saved and after == before:
        print("Nessuna nuova informazione salvata. Puoi rilanciare lo stesso comando quando vuoi continuare.")
        return 0

    print("\nAggiorno automaticamente l'analisi con la tua indicazione...")
    result = run_quiet(sld, layout, analysis_path, knowledge, feedback, log_path)
    print_summary(result, analysis_path, log_path)
    print("Per continuare, usa di nuovo LO STESSO comando. Non servono altri comandi o file da scegliere.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
