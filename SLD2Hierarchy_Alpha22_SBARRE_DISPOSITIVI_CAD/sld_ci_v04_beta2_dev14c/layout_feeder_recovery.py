"""Structural recovery of layout MV feeder trunks when native text labels are unreadable.

This module is deliberately conservative.  It never pretends to decode a corrupt
PDF text layer.  Instead it can identify repeated feeder *structures* from vector
geometry and retain any nearby raw header span as evidence.  Source labels remain
UNRESOLVED until readable text or operator confirmation is available.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, Iterable, List, Sequence, Tuple


def _merge_intervals(intervals: Sequence[Tuple[float, float]]) -> float:
    vals = sorted((min(a, b), max(a, b)) for a, b in intervals)
    if not vals:
        return 0.0
    total = 0.0
    s0, e0 = vals[0]
    for s, e in vals[1:]:
        if s <= e0 + 1.0:
            e0 = max(e0, e)
        else:
            total += max(0.0, e0 - s0)
            s0, e0 = s, e
    total += max(0.0, e0 - s0)
    return total


def _cluster_vertical_segments(vector_segments: Iterable[Any], page_w: float, page_h: float) -> List[Dict[str, Any]]:
    """Return x-clusters of long vertical conductor-like segments.

    A feeder trunk in an overview typically starts noticeably above the repeated
    CU rows and spans a substantial fraction of the page.  Border lines are
    excluded by margin and start-height gates.
    """
    min_seg_len = max(35.0, page_h * 0.035)
    x_tol = max(1.2, page_w * 0.0012)
    raw: List[Tuple[float, float, float]] = []
    for s in vector_segments or []:
        if getattr(s, "orientation", None) != "V":
            continue
        if float(getattr(s, "length_pt", 0.0)) < min_seg_len:
            continue
        x = float(getattr(s, "p1", (0.0, 0.0))[0])
        if not (page_w * 0.05 <= x <= page_w * 0.95):
            continue
        y0 = float(min(getattr(s, "p1", (0.0, 0.0))[1], getattr(s, "p2", (0.0, 0.0))[1]))
        y1 = float(max(getattr(s, "p1", (0.0, 0.0))[1], getattr(s, "p2", (0.0, 0.0))[1]))
        raw.append((x, y0, y1))

    if not raw:
        return []

    raw.sort(key=lambda t: t[0])
    groups: List[List[Tuple[float, float, float]]] = []
    for row in raw:
        if not groups:
            groups.append([row])
            continue
        gx = sum(x for x, _, _ in groups[-1]) / len(groups[-1])
        if abs(row[0] - gx) <= x_tol:
            groups[-1].append(row)
        else:
            groups.append([row])

    stats: List[Dict[str, Any]] = []
    for g in groups:
        x = sum(v[0] for v in g) / len(g)
        intervals = [(v[1], v[2]) for v in g]
        y_min = min(a for a, _ in intervals)
        y_max = max(b for _, b in intervals)
        coverage = _merge_intervals(intervals)
        if coverage < page_h * 0.30:
            continue
        # Exclude outer page frames and lower-level equipment internals.
        if not (page_h * 0.10 <= y_min <= page_h * 0.30):
            continue
        if y_max < page_h * 0.55:
            continue
        stats.append({
            "x": round(x, 3),
            "y_min": round(y_min, 3),
            "y_max": round(y_max, 3),
            "vertical_coverage_pt": round(coverage, 3),
            "segment_count": len(g),
        })

    if len(stats) < 2:
        return []

    # Top-level feeders tend to start at the same upper elevation.  Keep the
    # earliest coherent start band; this rejects CU enclosure sides that begin
    # lower on the sheet.
    top = min(s["y_min"] for s in stats)
    band = max(10.0, page_h * 0.025)
    stats = [s for s in stats if s["y_min"] <= top + band]
    if not (2 <= len(stats) <= 32):
        return []
    return sorted(stats, key=lambda s: s["x"])


def _native_spans(page: Any) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    try:
        raw = page.get_text("dict")
    except Exception:
        return out
    for block in raw.get("blocks", []) or []:
        for line in block.get("lines", []) or []:
            for span in line.get("spans", []) or []:
                text = str(span.get("text", "") or "").strip()
                bbox = span.get("bbox")
                if not text or not bbox:
                    continue
                out.append({"text": text, "bbox": [float(v) for v in bbox]})
    return out


def recover_layout_feeder_candidates(
    page: Any,
    page_no: int,
    doc_id: str,
    vector_segments: Iterable[Any],
) -> List[Dict[str, Any]]:
    """Recover structural feeder candidates without claiming unreadable labels.

    Each returned candidate is a real geometric feeder hypothesis.  When the
    nearest header span cannot be semantically decoded, ``line_instance_hint``
    stays ``None`` and a synthetic key is used solely for grouping.
    """
    page_w = float(page.rect.width)
    page_h = float(page.rect.height)
    trunks = _cluster_vertical_segments(vector_segments, page_w, page_h)
    if not trunks:
        return []

    spans = _native_spans(page)
    out: List[Dict[str, Any]] = []
    for idx, trunk in enumerate(trunks, 1):
        x = float(trunk["x"])
        y_top = float(trunk["y_min"])
        candidates = []
        for sp in spans:
            x0, y0, x1, y1 = sp["bbox"]
            cx = (x0 + x1) / 2.0
            cy = (y0 + y1) / 2.0
            if y1 > y_top + max(8.0, page_h * 0.01):
                continue
            if cy < y_top - page_h * 0.10:
                continue
            if abs(cx - x) > max(40.0, page_w * 0.04):
                continue
            # Prefer text almost directly above the trunk.
            score = abs(cx - x) + 0.35 * abs(y_top - y1)
            candidates.append((score, sp))
        header = min(candidates, key=lambda z: z[0])[1] if candidates else None
        if header:
            bbox = header["bbox"]
            raw_text = header["text"]
        else:
            bbox = [x - 8.0, max(0.0, y_top - 30.0), x + 8.0, y_top]
            raw_text = None

        out.append({
            "candidate_id": f"{doc_id}_P{page_no:03d}_FEEDER_{idx:02d}",
            "equipment_type": "MV_LINE",
            "anchor_role": "CANDIDATE",
            "evidence_kind": "STRUCTURAL_FEEDER_TRUNK_WITH_UNRESOLVED_LABEL",
            "page": page_no,
            "doc": doc_id,
            "bbox": [round(float(v), 3) for v in bbox],
            "raw_header_text": raw_text,
            "line_instance_hint": None,
            "synthetic_line_key": f"LAYOUT_FEEDER_{idx:02d}",
            "label_status": "UNRESOLVED",
            "source_status": "INFERRED",
            "trunk": trunk,
        })
    return out
